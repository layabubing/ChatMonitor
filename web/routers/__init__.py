"""
FastAPI 路由集合：按业务域拆分（认证/账户/概览/消息/提醒/报告/平台/文件/设置/实时流）。
每个模块导出一个 `router`，由 web/server.py 统一装配。
"""
from __future__ import annotations

from web.routers import (
    account,
    alerts,
    auth_routes,
    files,
    messages,
    overview,
    pages,
    platforms,
    reports,
    settings,
    stream,
)

# 装配顺序（路径互不冲突，顺序不影响匹配，仅为可读性归类）
all_routers = [
    pages.router,
    auth_routes.router,
    account.router,
    overview.router,
    messages.router,
    alerts.router,
    reports.router,
    platforms.router,
    files.router,
    settings.router,
    stream.router,
]

__all__ = ["all_routers"]
