"""
多进程启动器：每个平台 + web 各一个独立进程，互不干扰
—— 任一子进程异常退出会被自动重启（supervisor 语义）
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core import console  # noqa: E402
from config import PLATFORMS  # noqa: E402

console.setup()   # Windows 控制台 UTF-8，避免 emoji 日志崩溃

RESPAWN_MIN_UPTIME = 10   # 存活不足该秒数视为「启动即崩」，退避后再重启
RESPAWN_BACKOFF = 10


def launch_all() -> None:
    """启动并守护全部子进程。

    旧实现是「按顺序 p.wait()」，子进程退出后既不重启也不再监控：
    QQ worker 崩溃后永久失联（Web 仍正常，界面只显示「已停止」），
    必须人工重启整个服务才能恢复。这里改为轮询 + 自动重启。
    """
    from core import log as _log
    _log.setup("launcher")
    targets = [*PLATFORMS, "web"]
    procs: dict[str, tuple[subprocess.Popen, float]] = {}

    def spawn(target: str) -> None:
        p = subprocess.Popen(
            [sys.executable, str(BASE_DIR / "main.py"), target],
            cwd=str(BASE_DIR),
        )
        procs[target] = (p, time.time())
        print(f"[launcher] 已启动 {target} (pid={p.pid})", flush=True)

    print(f"[launcher] 启动全部进程: {', '.join(targets)} …", flush=True)
    for t in targets:
        spawn(t)

    try:
        while True:
            time.sleep(3)
            for t in targets:
                p, started = procs[t]
                code = p.poll()
                if code is None:
                    continue                      # 仍在运行
                uptime = time.time() - started
                if uptime < RESPAWN_MIN_UPTIME:   # 启动即崩 → 退避，避免刷屏
                    print(f"[launcher] {t} 启动后 {uptime:.1f}s 即退出 code={code}，"
                          f"{RESPAWN_BACKOFF}s 后重启", flush=True)
                    time.sleep(RESPAWN_BACKOFF)
                else:
                    print(f"[launcher] {t} 进程退出 code={code}，立即重启", flush=True)
                spawn(t)
    except KeyboardInterrupt:
        print("[launcher] 收到中断，正在关闭全部进程…", flush=True)
        for p, _ in procs.values():
            p.terminate()
        for p, _ in procs.values():
            try:
                p.wait(timeout=5)
            except Exception:  # noqa: BLE001
                p.kill()
