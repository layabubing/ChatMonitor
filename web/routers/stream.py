"""SSE 实时推送：后台增量轮询各租户数据库变化并广播；客户端事件流。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from config import PLATFORMS
from web import auth, deps, security, sse

router = APIRouter()

POLL_INTERVAL = 2.0


async def sse_poller() -> None:
    """后台增量扫描：所有用户各平台的新消息/提醒/报告/文件 → 按用户广播。
    （每用户每平台独立 try，单库异常不影响其余；杜绝阻塞主循环）"""
    cursor: dict[str, dict] = {}
    while True:
        try:
            for u in auth.list_users():
                uname = u["username"]
                cur = cursor.setdefault(uname, {"msg": {}, "alert": {}, "report": {}, "file": {}})
                for p in PLATFORMS:
                    try:
                        st = deps.storage(p, uname)
                        t = st.max_msg_ts(p)
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
                        a = st.max_alert_id(p)
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
                        r = st.max_report_id(p)
                        if r > cur["report"].get(p, 0):
                            cur["report"][p] = r
                            await sse.broadcast("report", {"platform": p}, username=uname)
                        f = st.max_file_id(p)
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
