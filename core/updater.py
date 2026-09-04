"""
版本更新：从 GitHub 仓库拉取最新 commit（每一次 commit 即一个新版本），不影响本地数据。

安全性设计：
- 本地数据（data/ logs/ reports/ configs/*.env 等）均在 .gitignore 中，git 不会触碰；
- 更新仅允许 fast-forward（git merge --ff-only）：本地有未提交改动或有未推送提交时拒绝执行，
  绝不覆盖/删除任何本地文件；
- 所有 git 操作带超时；网络失败只返回错误，不影响服务运行；
- check/apply 加锁防并发；GET status 只读内存缓存 + 本地 commit，不走网络。
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

from config import BASE_DIR

GIT_TIMEOUT = 60          # 单次 git 操作超时（秒）
PIP_TIMEOUT = 300         # 依赖安装超时（秒）
MAX_COMMITS = 50          # 待更新列表最多展示的 commit 数

_lock = threading.Lock()  # check/apply 互斥（防并发更新）

# 最近一次「检查更新」的内存缓存（进程内有效，重启后需重新检查）
_state: dict = {
    "checked_at": 0,      # 上次成功检查的时间戳（0=尚未检查）
    "remote": "",         # 跟踪的远端分支，如 origin/main
    "behind": 0,          # 落后远端多少个 commit
    "ahead": 0,           # 本地领先远端多少个 commit（>0 则禁止更新）
    "commits": [],        # 待更新的 commit 列表
    "error": "",          # 上次检查的错误信息
}


# ═══════════════ git 基础 ═══════════════
def _git(*args: str, timeout: int = GIT_TIMEOUT) -> tuple[bool, str]:
    """在仓库根目录执行 git，返回 (是否成功, 输出)。"""
    try:
        r = subprocess.run(
            ["git", "-C", str(BASE_DIR), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
        out = ((r.stdout or "") + (r.stderr or "")).strip()
        if r.returncode != 0 and "dubious ownership" in out:
            out += f"\n提示：请执行 git config --global --add safe.directory {BASE_DIR}"
        return r.returncode == 0, out
    except FileNotFoundError:
        return False, "服务器未安装 git，无法使用在线更新"
    except subprocess.TimeoutExpired:
        return False, f"git 操作超时（{timeout} 秒）"
    except Exception as e:  # noqa: BLE001
        return False, f"git 执行失败：{e}"


def _count(rev_range: str) -> int:
    """rev-list 计数（如 HEAD..origin/main），失败按 0 计。"""
    ok, out = _git("rev-list", "--count", rev_range)
    try:
        return int(out.strip()) if ok else 0
    except ValueError:
        return 0


def _parse_log(out: str) -> list[dict]:
    """解析 --format=%h%x1f%H%x1f%s%x1f%an%x1f%ad 输出为 commit 字典列表。"""
    commits = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) < 5:
            continue
        commits.append({
            "hash": parts[0], "full_hash": parts[1], "message": parts[2],
            "author": parts[3], "time": parts[4][:16],
        })
    return commits


def _current_commit() -> dict:
    """本地当前 commit（本地操作，不走网络）。"""
    ok, out = _git("log", "-1", "--format=%h%x1f%H%x1f%s%x1f%an%x1f%ad", "--date=iso")
    parsed = _parse_log(out) if ok else []
    return parsed[0] if parsed else {}


def _remote_ref() -> str:
    """当前分支跟踪的远端引用（如 origin/main），无上游时回退 origin/<当前分支>。"""
    ok, out = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if ok and out:
        return out
    ok, branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    branch = branch.strip() if ok and branch.strip() and branch.strip() != "HEAD" else "main"
    return f"origin/{branch}"


def repo_url() -> str:
    ok, out = _git("config", "--get", "remote.origin.url")
    return out if ok else ""


# ═══════════════ 状态 / 检查 / 更新 ═══════════════
def status() -> dict:
    """当前缓存状态（只读：本地 commit 实时取，远端信息用上次检查结果，不走网络）。"""
    s = dict(_state)
    s["current"] = _current_commit()
    s["repo"] = repo_url()
    s["update_available"] = s["behind"] > 0 and s["ahead"] == 0
    s["busy"] = _lock.locked()
    return s


def check() -> dict:
    """手动刷新：git fetch 后重新计算与远端的差距（网络操作，可能耗时数秒）。"""
    if not _lock.acquire(blocking=False):
        st = status()
        st["error"] = "另一个检查/更新正在进行，请稍后再试"
        return st
    try:
        ok, out = _git("fetch", "--prune", "origin")
        if not ok:
            last = out.splitlines()[-1] if out else "fetch 失败"
            _state["error"] = f"无法连接远端仓库：{last}"
            return status()
        remote = _remote_ref()
        behind = _count(f"HEAD..{remote}")
        ahead = _count(f"{remote}..HEAD")
        commits = []
        if behind:
            ok, out = _git("log", f"--format=%h%x1f%H%x1f%s%x1f%an%x1f%ad",
                           "--date=iso", "-n", str(MAX_COMMITS), f"HEAD..{remote}")
            commits = _parse_log(out) if ok else []
        _state.update(checked_at=int(time.time()), remote=remote, behind=behind,
                      ahead=ahead, commits=commits, error="")
        return status()
    finally:
        _lock.release()


def apply() -> dict:
    """确认更新：fast-forward 到远端最新 commit；本地数据（gitignore/未跟踪文件）不受影响。"""
    if not _lock.acquire(blocking=False):
        return {"ok": False, "error": "另一个检查/更新正在进行，请稍后再试"}
    try:
        ok, out = _git("fetch", "--prune", "origin")
        if not ok:
            return {"ok": False, "error": f"无法连接远端仓库：{out.splitlines()[-1] if out else ''}"}
        remote = _remote_ref()
        if _count(f"{remote}..HEAD") > 0:
            return {"ok": False, "error": "本地存在未推送的提交，为保护本地数据已取消更新"}
        behind = _count(f"HEAD..{remote}")
        if behind == 0:
            return {"ok": True, "updated": False, "message": "已是最新版本，无需更新"}
        ok, dirty = _git("status", "--porcelain", "--untracked-files=no")
        if dirty:
            return {"ok": False, "error": "本地代码存在未提交的修改，为保护本地数据已取消更新"}
        ok, old_head = _git("rev-parse", "HEAD")
        ok, out = _git("merge", "--ff-only", remote)
        if not ok:
            return {"ok": False, "error": f"更新失败：{out}"}

        # requirements.txt 有变化 → 用当前运行的 Python 重装依赖（失败仅提示，不阻断）
        warning = ""
        ok, names = _git("diff", "--name-only", f"{old_head}..HEAD")
        if ok and "requirements.txt" in names.splitlines():
            try:
                r = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r",
                     str(BASE_DIR / "requirements.txt")],
                    capture_output=True, text=True, timeout=PIP_TIMEOUT,
                )
                if r.returncode != 0:
                    warning = "代码已更新，但依赖安装失败，请手动执行 pip install -r requirements.txt"
            except Exception:  # noqa: BLE001
                warning = "代码已更新，但依赖安装超时/失败，请手动执行 pip install -r requirements.txt"

        _state.update(checked_at=int(time.time()), behind=0, ahead=0, commits=[], error="")
        cur = _current_commit()
        return {"ok": True, "updated": True,
                "message": f"已更新到 {cur.get('hash', '')}（{behind} 个提交）",
                "current": cur, "warning": warning}
    finally:
        _lock.release()


def restart_services() -> str:
    """更新后重启：向各平台 worker 下发 restart 命令（systemd 自动拉起）；
    web 进程自身在 systemd 下延迟退出由 Restart=always 拉起。
    返回 'auto'（systemd 环境自动重启）或 'manual'（需人工重启）。"""
    if os.environ.get("INVOCATION_ID"):  # 由 systemd 启动
        from config import PLATFORMS
        from core import commands
        for p in PLATFORMS:
            try:
                commands.write_command(p, "restart")
            except Exception:  # noqa: BLE001  单个 worker 失败不影响其余
                pass

        def _delayed_exit() -> None:
            time.sleep(1.5)   # 先让 HTTP 响应发出去
            os._exit(0)

        threading.Thread(target=_delayed_exit, daemon=True).start()
        return "auto"
    return "manual"
