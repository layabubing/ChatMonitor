"""
SSE 广播管理器：维护客户端队列集合，向在线浏览器推送事件（多租户：按用户隔离）
（web 进程内使用，poller 由 server.py 的 lifespan 启动）
"""
from __future__ import annotations

import asyncio
import json

_clients: dict[str, set] = {}   # username -> set[Queue]
_user_clients: dict[str, int] = {}
MAX_PER_USER = 3   # 每个登录用户最多 N 个 SSE 连接（防资源耗尽）


def add_client(username: str, q: asyncio.Queue) -> None:
    n = _user_clients.get(username, 0)
    if n >= MAX_PER_USER:
        raise ConnectionError("SSE 连接过多")
    _clients.setdefault(username, set()).add(q)
    _user_clients[username] = n + 1


def remove_client(username: str, q: asyncio.Queue) -> None:
    if username in _clients:
        _clients[username].discard(q)
        if not _clients[username]:
            _clients.pop(username, None)
    if username:
        _user_clients[username] = max(0, _user_clients.get(username, 1) - 1)


def client_count() -> int:
    return sum(len(s) for s in _clients.values())


async def broadcast(event: str, data: dict, username: str = "") -> None:
    """推送事件：username 指定时只推给该用户；否则推给全局客户端"""
    if username:
        qs = set(_clients.get(username, set()))
    else:
        qs = set().union(*_clients.values()) if _clients else set()
    if not qs:
        return
    for q in list(qs):
        try:
            q.put_nowait((event, data))
        except Exception:  # noqa: BLE001  清理失效连接
            for s in list(_clients.values()):
                s.discard(q)


def sse_frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
