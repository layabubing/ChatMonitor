"""设置：读取用户级配置汇总、保存用户级关键词库。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

import config
from config import PLATFORMS
from core import commands
from web import auth, deps

router = APIRouter()


@router.get("/api/settings")
async def api_settings(request: Request):
    user = deps.require_user(request)
    # 多租户：平台绑定与关键词均为【用户级】；AI 模型为全局（管理员统一提供 API）
    app_cfg = config.get_app_config()
    platforms = []
    for p in PLATFORMS:
        b = auth.get_user_binding(user["username"], p)
        cfg = (b or {}).get("config", {}) or {}
        platforms.append({
            "name": p,
            "enabled": bool((b or {}).get("enabled")),
            "groups": cfg.get("DINGTALK_CHAT_IDS" if p == "dingtalk" else "QQ_GROUP_OPENIDS", ""),
            "report_time": f"{app_cfg.get('REPORT_HOUR', '18')}:{app_cfg.get('REPORT_MINUTE', '0')}",
            "running": deps.is_alive(p, user["username"]),
        })
    return {
        "role": user["role"],
        "username": user["username"],
        "nickname": user.get("nickname", ""),
        "keywords": auth.get_user_keywords(user["username"]),
        "platforms": platforms,
        "ai": {"model": app_cfg.get("AI_MODEL"), "base_url": app_cfg.get("AI_BASE_URL"),
               "key_set": bool(app_cfg.get("AI_API_KEY")), "key_masked": deps.mask(app_cfg.get("AI_API_KEY"))},
        "serverchan_set": bool(app_cfg.get("SERVERCHAN_KEY")),
        "register_open": app_cfg.get("REGISTER_OPEN", "true") == "true",
    }


@router.post("/api/settings/keywords")
async def api_save_keywords(request: Request):
    """保存【当前用户自己的】关键词库（多租户，无需管理员）。"""
    user = deps.require_user(request)
    body = await request.json()
    cats = body.get("categories")
    if not isinstance(cats, dict):
        raise HTTPException(400, "参数错误")
    auth.save_user_keywords(user["username"], cats)
    # 通知对应平台 worker 重载（按用户命令文件，只重载该用户实例）
    for p in PLATFORMS:
        commands.write_command(p, "reload_keywords", username=user["username"])
    return {"ok": True}
