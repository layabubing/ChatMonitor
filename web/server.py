"""
Web 服务装配：创建 FastAPI 应用，挂载静态资源、CSRF 中间件、SSE 后台轮询，注册各业务路由。
（仅监听 127.0.0.1，由 Nginx 反代对外；具体逻辑见 web/routers/*、web/deps、web/security）
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# 向后兼容 re-export（既有工具/测试可能引用）：
from config import LOGS_DIR, platform_db_path  # noqa: F401
from web import security
from web.routers import all_routers
from web.routers.stream import sse_poller

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时开启 SSE 轮询任务（后台增量扫描数据库变化并广播）。"""
    task = asyncio.create_task(sse_poller())
    try:
        yield
    finally:
        task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="聊天智能分析助手", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.middleware("http")(security.csrf_guard)
    for router in all_routers:
        app.include_router(router)
    return app


app = create_app()
