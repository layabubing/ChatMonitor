"""提醒：分页查询（可跨平台聚合）、标记已读。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from config import PLATFORMS
from web import deps

router = APIRouter()


@router.get("/api/alerts")
async def api_alerts(request: Request, platform: str = "", unread: bool = False,
                     page: int = 1, page_size: int = 50):
    user = deps.require_user(request)
    ps = deps.page_size(page_size)
    if platform and platform not in PLATFORMS:
        raise HTTPException(400, "未知平台")
    if platform:
        return deps.storage(platform, user["username"]).query_alerts(
            platform=platform, unread_only=unread, page=page, page_size=ps)
    # 空平台：聚合全部平台（取足量后全局排序，正确分页）
    fetch = min(page * ps, 500)
    items, total = [], 0
    for p in PLATFORMS:
        d = deps.storage(p, user["username"]).query_alerts(
            platform=p, unread_only=unread, page=1, page_size=fetch)
        items += d["items"]
        total += d["total"]
    items.sort(key=lambda a: a["ts"], reverse=True)
    start = (page - 1) * ps
    return {"total": total, "page": page, "page_size": ps, "items": items[start:start + ps]}


@router.post("/api/alerts/read")
async def api_alerts_read(request: Request):
    user = deps.require_user(request)
    body = await request.json()
    ids = body.get("ids") or None
    platform = body.get("platform", "")
    if platform and platform not in PLATFORMS:
        raise HTTPException(400, "未知平台")
    updated = 0
    if platform:
        updated += deps.storage(platform, user["username"]).mark_alerts_read(ids=ids, platform=platform)
    else:
        for p in PLATFORMS:
            updated += deps.storage(p, user["username"]).mark_alerts_read(ids=ids, platform=p)
    return {"ok": True, "updated": updated}
