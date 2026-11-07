"""SSE 实时推送：后台增量轮询各租户数据库变化并广播；客户端事件流。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from config import PLATFORMS
from web import auth, deps, security, sse

router = APIRouter()

POLL_INTERVAL = 2.0          # 有客户端在线时的增量扫描间隔
IDLE_POLL_INTERVAL = 10.0    # 无客户端时的空转间隔（不扫库）


async def sse_poller() -> None:
    """后台增量扫描：所有用户各平台的新消息/提醒/报告/文件 → 按用户广播。

    性能要点（原实现每 2s 无条件扫「用户×平台×4 类」，约 16N 次查询）：
    - **无客户端时零查询**：清空基线后长休眠；重连后从当前最大值重建基线（不会补发历史）；
    - 有客户端时用 `Storage.max_ids()` **一次连接取四类最大值**（原为 4 次连接）；
    - 每用户每平台独立 try，单库异常不影响其余。
    """
    cursor: dict[str, dict] = {}
    while True:
        if sse.client_count() == 0:
            cursor.clear()
            await asyncio.sleep(IDLE_POLL_INTERVAL)
            continue
        try:
            for u in auth.list_users():
                uname = u["username"]
                cur = cursor.setdefault(uname, {"msg": {}, "alert": {}, "report": {}, "file": {}})
                for p in PLATFORMS:
                    try:
                        st = deps.storage(p, uname)
                        latest_ids = st.max_ids(p)
                        t = latest_ids["msg"]
                        if t > cur["msg"].get(p, 0):
                            cur["msg"][p] = t
                            payload: dict = {"platform": p}
                            latest = st.latest_message(p)
                            if latest:  # 摘要载荷：移动端可直接展示/通知，网页端忽略多余字段
                                payload.update({
                                    "group_name": latest.get("group_name", ""),
                                    "sender": latest.get("sender", ""),
                                    "preview": (latest.get("content") or "")[:50],
                                })
                            await sse.broadcast("message", payload, username=uname)
                        a = latest_ids["alert"]
                        if a > cur["alert"].get(p, 0):
                            cur["alert"][p] = a
                            payload = {"platform": p, "id": a}
                            alert = st.get_alert(a)
                            if alert:
                                payload.update({
                                    "priority": alert.get("priority", ""),
                                    "group_name": alert.get("group_name", ""),
                                    "preview": (alert.get("content") or "")[:50],
                                })
                            await sse.broadcast("alert", payload, username=uname)
                        r = latest_ids["report"]
                        if r > cur["report"].get(p, 0):
                            cur["report"][p] = r
                            await sse.broadcast("report", {"platform": p}, username=uname)
                        f = latest_ids["file"]
                        if f > cur["file"].get(p, 0):
                            cur["file"][p] = f
                            await sse.broadcast("file", {"platform": p}, username=uname)
                    except Exception as e:  # noqa: BLE001
                        security.log().warning(f"[sse] poller 异常 ({uname}/{p}): {e}")
        except Exception as e:  # noqa: BLE001
            security.log().warning(f"[sse] poller 整体异常: {e}")
        await asyncio.sleep(POLL_INTERVAL)


@router.get("/api/stream")
async def api_stream(request: Request):
    """SSE 事件流：message / alert / report / file / ready（每用户最多 3 连接）。"""
    user = auth.check_login(request)
    if not user:
        raise HTTPException(401, "未登录")
    q: asyncio.Queue = asyncio.Queue()
    try:
        sse.add_client(user["username"], q)
    except ConnectionError:
        raise HTTPException(429, "连接数过多，请关闭部分页面")
    username = user["username"]

    async def gen():
        try:
            yield sse.sse_frame("ready", {})
            while True:
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=20)
                    yield sse.sse_frame(event, data)
                except TimeoutError:
                    yield ": ping\n\n"   # 保活注释
        finally:
            sse.remove_client(username, q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
