"""文件库与媒体访问（多租户：严格限制在用户自己目录内）。"""
from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from config import DATA_DIR, PLATFORMS
from web import deps

router = APIRouter()


@router.get("/api/media/raw")
async def api_media_raw(request: Request, path: str = ""):
    """按本地相对路径返回媒体文件（仅允许 users/{username}/media/ 下）。"""
    user = deps.require_user(request)
    uname = user["username"]
    if not path.startswith(f"users/{uname}/media/"):
        raise HTTPException(400, "非法路径")
    full = (DATA_DIR / path).resolve()
    if not str(full).startswith(str(DATA_DIR.resolve())):
        raise HTTPException(400, "非法路径")
    if not full.exists() or not full.is_file():
        raise HTTPException(404, "文件不存在")
    mime = mimetypes.guess_type(full.name)[0] or "application/octet-stream"
    return FileResponse(full, media_type=mime)


@router.get("/api/files")
async def api_files(request: Request, platform: str = "", category: str = "",
                    important: str = "", q: str = "", page: int = 1, page_size: int = 50):
    user = deps.require_user(request)
    ps = deps.page_size(page_size)
    important_only = str(important).lower() in ("1", "true", "yes", "on")
    if platform:
        return deps.storage(platform, user["username"]).query_files(
            platform=platform, important_only=important_only, category=category,
            q=q, page=page, page_size=ps)
    fetch = min(page * ps, 500)
    items, total = [], 0
    for p in PLATFORMS:
        d = deps.storage(p, user["username"]).query_files(
            platform=p, important_only=important_only, category=category, q=q, page=1, page_size=fetch)
        items += d["items"]
        total += d["total"]
    items.sort(key=lambda f: f["ts"], reverse=True)
    start = (page - 1) * ps
    return {"total": total, "page": page, "page_size": ps, "items": items[start:start + ps]}


@router.get("/api/files/categories")
async def api_file_categories(request: Request):
    user = deps.require_user(request)
    cats = set()
    for p in PLATFORMS:
        cats.update(deps.storage(p, user["username"]).file_categories())
    return {"items": sorted(cats)}


@router.get("/api/files/{platform}/{fid}/raw")
async def api_file_raw(platform: str, fid: int, request: Request):
    user = deps.require_user(request)
    if platform not in PLATFORMS:
        raise HTTPException(400, "未知平台")
    f = deps.storage(platform, user["username"]).get_file(fid)
    if not f:
        raise HTTPException(404, "文件不存在")
    local = f["local_path"]
    if not local.startswith(f"users/{user['username']}/media/"):
        raise HTTPException(400, "非法文件路径")
    path = DATA_DIR / local
    if not path.exists():
        raise HTTPException(404, "文件已丢失")
    mime = (mimetypes.guess_type(f["orig_name"])[0]
            or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    return FileResponse(path, media_type=mime)


@router.post("/api/files/{platform}/{fid}/important")
async def api_file_important(platform: str, fid: int, request: Request):
    user = deps.require_user(request)
    if platform not in PLATFORMS:
        raise HTTPException(400, "未知平台")
    body = await request.json()
    val = 1 if body.get("important") else 0
    if not deps.storage(platform, user["username"]).set_file_important(fid, val):
        raise HTTPException(404, "文件不存在")
    return {"ok": True, "important": val}
