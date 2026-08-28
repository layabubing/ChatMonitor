"""报告：列表、HTML 预览、docx 下载（带路径穿越防护与旧数据兼容）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from config import PLATFORMS
from web import deps

router = APIRouter()

_HTML_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'none'; style-src 'unsafe-inline'; "
        "img-src 'self' data:; base-uri 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
}
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/api/reports")
async def api_reports(request: Request, platform: str = ""):
    user = deps.require_user(request)
    if platform and platform not in PLATFORMS:
        raise HTTPException(400, "未知平台")
    if platform:
        return {"items": deps.storage(platform, user["username"]).query_reports(platform)}
    items = []
    for p in PLATFORMS:
        items += deps.storage(p, user["username"]).query_reports(p)
    items.sort(key=lambda r: r["date"], reverse=True)
    return {"items": items}


@router.get("/api/reports/{platform}/{date}/html")
async def api_report_html(platform: str, date: str, request: Request):
    user = deps.require_user(request)
    deps.validate_report(platform, date)
    path = deps.resolve_report_file(platform, date, user, "html")
    return FileResponse(path, media_type="text/html", headers=_HTML_HEADERS)


@router.get("/api/reports/{platform}/{date}/docx")
async def api_report_docx(platform: str, date: str, request: Request):
    user = deps.require_user(request)
    deps.validate_report(platform, date)
    path = deps.resolve_report_file(platform, date, user, "docx")
    return FileResponse(path, filename=f"{platform}-{date}-日报.docx", media_type=_DOCX_MIME)
