"""消息：群列表、分页/搜索查询。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from config import PLATFORMS
from web import deps

router = APIRouter()


@router.get("/api/groups")
async def api_groups(request: Request, platform: str = Query(...)):
    user = deps.require_user(request)
    if platform not in PLATFORMS:
        raise HTTPException(400, "未知平台")
    return {"items": deps.storage(platform, user["username"]).distinct_groups(platform)}


@router.get("/api/messages")
async def api_messages(request: Request, platform: str = Query(...), group: str = "",
                       q: str = "", page: int = 1, page_size: int = 50):
    user = deps.require_user(request)
    if platform not in PLATFORMS:
        raise HTTPException(400, "未知平台")
    return deps.storage(platform, user["username"]).query_messages(
        platform, group=group, q=q, page=page, page_size=deps.page_size(page_size))
