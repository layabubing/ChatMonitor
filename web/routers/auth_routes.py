"""认证路由：登录（含限流）、注册（含开关/邀请码/频控）、登出、当前用户。"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

import config
from web import auth, security

router = APIRouter()


@router.post("/api/login")
async def api_login(request: Request):
    body = await request.json()
    username = (body.get("username", "") or "").strip()
    ip = security.client_ip(request)
    key = f"{ip}|{username}"

    locked = security.login_locked(key)
    if locked:
        security.log().warning(f"[auth] 登录锁定中: {username} from {ip} (剩余{locked}s)")
        return JSONResponse({"error": f"尝试次数过多，请 {locked} 秒后重试"}, status_code=429)

    token = auth.do_login(username, body.get("password", ""))
    if not token:
        wait = security.record_login_fail(key)
        if wait:
            security.log().warning(f"[auth] 触发限流锁定: {username} from {ip}")
        else:
            security.log().warning(f"[auth] 登录失败: {username} from {ip}")
        return JSONResponse({"error": "用户名或密码错误"}, status_code=401)

    security.clear_login_fails(key)
    security.log().info(f"[auth] 登录成功: {username} from {ip}")
    resp = JSONResponse({"ok": True})
    auth.set_auth_cookie(resp, token)
    return resp


@router.post("/api/register")
async def api_register(request: Request):
    """开放注册（可用 REGISTER_OPEN / REGISTER_INVITE_CODE 控制；按 IP 限频防批量注册）。"""
    cfg = config.get_app_config()
    if cfg.get("REGISTER_OPEN", "true") != "true":
        return JSONResponse({"error": "当前未开放注册"}, status_code=403)
    ip = security.client_ip(request)
    if security.register_throttled(ip):
        return JSONResponse({"error": "注册过于频繁，请稍后再试"}, status_code=429)
    invite = cfg.get("REGISTER_INVITE_CODE", "") or ""
    body = await request.json()
    if invite and (body.get("invite_code") or "") != invite:
        security.log().warning(f"[auth] 注册邀请码错误: {(body.get('username') or '')[:20]} from {ip}")
        return JSONResponse({"error": "邀请码错误"}, status_code=400)
    ok, msg = auth.register(body.get("username", ""), body.get("password", ""))
    if not ok:
        return JSONResponse({"error": msg}, status_code=400)
    security.record_register(ip)
    security.log().info(f"[auth] 新用户注册: {(body.get('username') or '')[:20]} from {ip}")
    return {"ok": True, "msg": msg}


@router.post("/api/logout")
async def api_logout(response: Response):
    resp = JSONResponse({"ok": True})
    auth.clear_auth_cookie(resp)
    return resp


@router.get("/api/me")
async def api_me(request: Request):
    user = auth.check_login(request)
    if not user:
        return JSONResponse({"error": "未登录"}, status_code=401)
    return {"username": user["username"], "role": user["role"], "nickname": user.get("nickname", "")}
