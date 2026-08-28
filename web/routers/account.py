"""个人中心：修改昵称、修改密码（大平台规则：改自己需验证旧密码，改他人需管理员）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from web import auth, deps

router = APIRouter()


@router.post("/api/me/nickname")
async def api_me_nickname(request: Request):
    """修改自己的昵称（无需管理员授权）。"""
    user = deps.require_user(request)
    body = await request.json()
    nickname = (body.get("nickname") or "").strip()
    if len(nickname) > 24:
        raise HTTPException(400, "昵称最多 24 个字符")
    if not auth.update_nickname(user["username"], nickname):
        raise HTTPException(400, "昵称修改失败")
    return {"ok": True, "nickname": nickname or user["username"]}


@router.post("/api/settings/password")
async def api_change_password(request: Request):
    """修改密码：普通用户仅能改自己（需旧密码），管理员可改他人。"""
    user = deps.require_user(request)
    body = await request.json()
    target = (body.get("username") or "").strip() or user["username"]
    old_pwd = body.get("old_password", "")
    new_pwd = body.get("password", "")
    if user["role"] != "admin" and target != user["username"]:
        raise HTTPException(403, "普通用户仅能修改自己的密码")
    if target == user["username"] and not auth.verify_password(user["username"], old_pwd):
        raise HTTPException(400, "旧密码不正确")
    if not auth.update_password(target, new_pwd):
        raise HTTPException(400, "密码至少 6 位或用户不存在")
    return {"ok": True, "username": target}
