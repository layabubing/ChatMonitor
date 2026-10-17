"""
Web 共享依赖：多租户 Storage 获取、运行状态判断、鉴权辅助、分页/脱敏、报告文件解析。
供各 router 复用，避免逻辑散落在路由函数里。
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import HTTPException, Request

import config
from config import DATA_DIR, PLATFORMS, get_platform_config
from core import accounts
from core.storage import Storage
from web import auth

_storage_cache: dict[str, Storage] = {}


def storage(platform: str, username: str = "") -> Storage:
    """多租户：username 指定时返回该用户的独立 Storage，否则全局（旧数据兼容）。"""
    key = f"{username}|{platform}" if username else platform
    if key not in _storage_cache:
        if username:
            config.ensure_user_dirs(username)
            _storage_cache[key] = Storage(config.user_platform_db_path(username, platform))
        else:
            _storage_cache[key] = Storage(config.platform_db_path(platform))
    return _storage_cache[key]


def _alive_file(platform: str, username: str = "") -> Path | None:
    """解析心跳文件路径（多租户：全局实例 vs 用户独立实例，口径与 main._collect_instances 一致）。
    未绑定/未启用时返回 None。"""
    global_cfg = get_platform_config(platform)
    global_enabled = global_cfg.get(f"{platform.upper()}_ENABLED", "false") == "true"
    app_id_key = config.PLATFORM_META[platform]["app_id_key"]
    global_id = global_cfg.get(app_id_key, "")
    if username:
        b = accounts.get_user_binding(username, platform)
        if not b or not b.get("enabled"):
            return None   # 未绑定/未启用 → 无实例
        # 与 main._collect_instances 保持同一口径：用户未填写的键沿用全局值。
        # 若只读用户绑定（无全局兜底），会出现「worker 判定复用全局实例而不建用户实例，
        # web 却去查用户目录心跳」的不一致 → 界面永久显示「已停止」。
        merged = dict(global_cfg)
        merged.update(b.get("config") or {})
        user_id = merged.get(app_id_key, "")
        # 仅当全局启用 且 凭证与全局相同 → 共享全局实例；否则用户独立实例
        if global_enabled and user_id and user_id == global_id:
            return DATA_DIR / f"{platform}.alive"
        return config.user_data_dir(username) / f"{platform}.alive"
    return DATA_DIR / f"{platform}.alive"


def platform_runtime(platform: str, username: str = "") -> dict:
    """平台运行状态细分（供界面区分「没在跑」与「在跑但连不上」）：
    - alive：worker 进程存活（心跳新鲜，<120s）
    - ready：连接已就绪、可正常收消息（如 QQ 需通过 READY 认证）

    心跳内容为「时间戳:连接是否就绪」；兼容旧格式（纯时间戳 → ready 跟随 alive）。"""
    p = _alive_file(platform, username)
    if p is None or not p.exists():
        return {"alive": False, "ready": False}
    try:
        raw = p.read_text().strip()
        ts_s, _, conn = raw.partition(":")
        ts = int(ts_s)
        alive = time.time() - ts < 120
        ready = alive and conn.strip() != "0"
        return {"alive": alive, "ready": ready}
    except Exception:  # noqa: BLE001
        return {"alive": False, "ready": False}


def is_alive(platform: str, username: str = "") -> bool:
    """worker 是否在运行**且**连接就绪（语义：能否正常收消息）。"""
    return platform_runtime(platform, username)["ready"]


# ── 鉴权辅助 ──
def require_user(request: Request) -> dict:
    """登录即可；未登录 401。"""
    try:
        return auth.require_login(request)
    except PermissionError:
        raise HTTPException(401, "未登录")


def require_admin(request: Request) -> dict:
    """需要管理员；未登录 401，普通用户 403。"""
    user = require_user(request)
    if user["role"] != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user


# ── 分页/脱敏 ──
def page_size(n: int) -> int:
    """分页大小上限（防超大查询 DoS）。"""
    return min(max(1, int(n)), 200)


def mask(text: str) -> str:
    t = text or ""
    return t[:4] + "*" * 6 + t[-4:] if len(t) > 12 else "******"


def mask_platform_config(name: str, cfg: dict) -> dict:
    """平台配置脱敏返回（密钥只回显掩码；由 PLATFORM_META 注册表驱动）。"""
    out = {}
    meta = config.PLATFORM_META.get(name, {})
    secret_keys = set(meta.get("secret_keys", []))
    for k in meta.get("keys", []):
        v = cfg.get(k, "")
        if k in secret_keys:
            out[k] = mask(v)
            out[k + "_SET"] = bool(v)
        else:
            out[k] = v
    return out


# ── 报告 ──
def validate_report(platform: str, date: str) -> None:
    """防路径穿越：严格校验 platform 与 date 格式。"""
    if platform not in PLATFORMS or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise HTTPException(400, "非法参数")


def resolve_report_file(platform: str, date: str, user: dict, kind: str) -> Path:
    """解析某日报文件的真实路径（kind='html'|'docx'），带路径穿越防护与旧数据兼容。"""
    from config import REPORTS_DIR, platform_report_dir, user_data_dir, user_report_dir
    suffix = ".html" if kind == "html" else ".docx"
    db_field = "html_path" if kind == "html" else "docx_path"
    username = user["username"]
    # 1. 优先用数据库记录里的真实路径（兼容历史数据/路径迁移/旧版全局 reports）
    try:
        for r in storage(platform, username).query_reports(platform):
            if r["date"] == date and r.get(db_field):
                p = Path(r[db_field])
                allowed = [str(user_data_dir(username)), str(REPORTS_DIR)]
                if any(str(p).startswith(a) for a in allowed) and p.exists():
                    return p
    except Exception:  # noqa: BLE001
        pass
    # 2. 回退：重构标准用户目录路径
    path = user_report_dir(username, platform) / f"{date}-日报{suffix}"
    if path.exists():
        return path
    # 3. 兼容旧版全局 reports/（admin 历史数据）
    legacy = platform_report_dir(platform) / f"{date}-日报{suffix}"
    if user["role"] == "admin" and legacy.exists():
        return legacy
    raise HTTPException(404, "报告不存在")
