"""
多进程启动器：每个平台 + web 各一个独立进程，互不干扰
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core import console  # noqa: E402

console.setup()   # Windows 控制台 UTF-8，避免 emoji 日志崩溃


def launch_all() -> None:
    procs = []
    targets = ["qq", "dingtalk", "web"]
    print("[launcher] 启动全部进程: qq, dingtalk, web …")
    for t in targets:
        p = subprocess.Popen(
            [sys.executable, str(BASE_DIR / "main.py"), t],
            cwd=str(BASE_DIR),
        )
        procs.append((t, p))
        print(f"[launcher] 已启动 {t} (pid={p.pid})")

    try:
        for name, p in procs:
            code = p.wait()
            print(f"[launcher] {name} 进程退出，code={code}（其余进程不受影响）")
    except KeyboardInterrupt:
        print("[launcher] 收到中断，正在关闭全部进程…")
        for _, p in procs:
            p.terminate()
        for _, p in procs:
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
