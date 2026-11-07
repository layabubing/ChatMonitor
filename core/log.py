"""统一日志基础设施：控制台 + 按进程分文件 + 捕获 print 输出。

设计取舍：
- 代码里有 100+ 处 `print(...)`，逐一改成 logging 改动面过大且易引入回归；
- 这里用 `_TeeStream` 把 stdout 同时写到「本进程日志文件」，**print 自动落盘**且保留终端实时性；
- 每个进程写自己的文件（`data/logs/{component}.log`），避免多进程抢同一个 RotatingFileHandler；
- `RotatingFileHandler` 单文件 10MB × 5 份，防止无限增长。
"""
from __future__ import annotations

import io
import logging
import logging.handlers
import sys
import threading

from config import LOGS_DIR

_configured = False
_tee: _TeeStream | None = None
_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


class _TeeStream(io.TextIOBase):
    """把写入同时转发到原始流与日志文件（任一侧失败都不影响另一侧）。"""

    def __init__(self, origin, file_obj):
        self._origin = origin
        self._file = file_obj
        self._lock = threading.Lock()

    def write(self, s):  # noqa: D102
        with self._lock:
            try:
                self._origin.write(s)
            except Exception:  # noqa: BLE001
                pass
            try:
                self._file.write(s)
                self._file.flush()   # 及时刷盘：进程崩溃时也能留下最后几行
            except Exception:  # noqa: BLE001
                pass
        return len(s)

    def flush(self):  # noqa: D102
        with self._lock:
            for f in (self._origin, self._file):
                try:
                    f.flush()
                except Exception:  # noqa: BLE001
                    pass

    def isatty(self):  # noqa: D102
        try:
            return self._origin.isatty()
        except Exception:  # noqa: BLE001
            return False


def setup(component: str = "app", level: int = logging.INFO) -> logging.Logger:
    """初始化日志（同进程幂等）。`component` 决定文件名：`data/logs/{component}.log`。"""
    global _configured, _tee
    logger = logging.getLogger(component)
    if _configured:
        return logger

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"{component}.log"

    fmt = logging.Formatter(_LOG_FMT, datefmt=_DATE_FMT)
    root = logging.getLogger()
    root.setLevel(level)
    try:
        fh = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:  # noqa: BLE001  文件不可写时退化为仅控制台
        pass
    try:
        sh = logging.StreamHandler(stream=sys.__stdout__)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    except Exception:  # noqa: BLE001
        pass

    # 关键：print() 也落盘（保留终端输出），无需改 100+ 处调用
    try:
        raw = open(log_path, "a", encoding="utf-8", buffering=1)  # 行缓冲
        _tee = _TeeStream(sys.__stdout__, raw)
        sys.stdout = _tee
    except Exception:  # noqa: BLE001
        pass

    _configured = True
    logger.info("日志已初始化 → %s", log_path)
    return logger


def get(name: str = "app") -> logging.Logger:
    """取命名 logger（未初始化也能安全使用）。"""
    return logging.getLogger(name)
