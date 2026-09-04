"""版本更新：仅 admin 可查看状态 / 手动刷新 / 确认更新（每一次 commit 即一个版本）。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from core import updater
from web import deps, security

router = APIRouter()


@router.get("/api/update/status")
async def api_update_status(request: Request):
    """缓存的更新状态（不走网络；远端信息为上次「检查更新」的结果）。"""
    deps.require_admin(request)
    return updater.status()


@router.post("/api/update/check")
async def api_update_check(request: Request):
    """手动刷新：git fetch 远端仓库，重新计算落后多少 commit。"""
    user = deps.require_admin(request)
    security.log().info("[update] %s 手动检查更新", user["username"])
    return await asyncio.to_thread(updater.check)


@router.post("/api/update/apply")
async def api_update_apply(request: Request):
    """确认更新：fast-forward 到远端最新 commit，成功后按环境自动/提示重启服务。"""
    user = deps.require_admin(request)
    result = await asyncio.to_thread(updater.apply)
    if result.get("ok") and result.get("updated"):
        security.log().info("[update] %s 确认更新：%s", user["username"], result.get("message"))
        result["restart"] = updater.restart_services()
    elif not result.get("ok"):
        security.log().info("[update] %s 更新失败：%s", user["username"], result.get("error"))
    return result
