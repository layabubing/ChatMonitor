"""概览：各平台消息/提醒统计与运行状态。"""
from __future__ import annotations

from fastapi import APIRouter, Request

from config import PLATFORMS
from web import deps

router = APIRouter()


@router.get("/api/overview")
async def api_overview(request: Request):
    user = deps.require_user(request)
    result = {}
    for p in PLATFORMS:
        st = deps.storage(p, user["username"])
        ov = st.overview()
        ov["running"] = deps.is_alive(p, user["username"])
        ov["today_messages"] = st.count_messages_today(p)
        result[p] = ov
    return result
