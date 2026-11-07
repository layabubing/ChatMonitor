"""同步代码里运行协程的工具：复用线程本地事件循环。

背景：此前 5 处代码（pipeline / reporter / 三个平台适配器）在每次调用时
`asyncio.new_event_loop()` + `close()`，高频路径（每条媒体消息、每条 @ 消息）
都会创建并销毁一个事件循环（约 1-3ms + 句柄分配）。

这里改为**线程本地缓存**：每个工作线程复用同一个 loop，进程内不再反复创建。
"""
from __future__ import annotations

import asyncio
import threading

_local = threading.local()


def run_async(coro):
    """在当前线程运行协程并返回结果；复用该线程的 loop（无则创建并缓存）。"""
    loop = getattr(_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _local.loop = loop
    return loop.run_until_complete(coro)


def close_local_loop() -> None:
    """关闭当前线程缓存的 loop（测试清理/进程退出时可选调用）。"""
    loop = getattr(_local, "loop", None)
    if loop is not None and not loop.is_closed():
        loop.close()
    _local.loop = None
