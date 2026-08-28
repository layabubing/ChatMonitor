"""静态页面：仪表盘 SPA 与登录页。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

router = APIRouter()

# HTML 外壳不做启发式缓存：每次请求都向服务器重校验，
# 避免前端改版后浏览器用旧 HTML 引用已变更/删除的静态资源
_NO_CACHE = {"Cache-Control": "no-cache"}


@router.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"), headers=_NO_CACHE)


@router.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse((STATIC_DIR / "login.html").read_text(encoding="utf-8"), headers=_NO_CACHE)
