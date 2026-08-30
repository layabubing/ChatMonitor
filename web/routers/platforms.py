"""平台控制与账号绑定（多租户：均作用于当前用户自己的实例）。"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

import config
from config import PLATFORMS
from core import commands
from web import auth, deps, security
from web.envutil import allowed_keys

router = APIRouter()

_COMMANDS = ("generate_report", "pause", "resume", "reload_keywords", "restart")


# ── 平台控制命令 ──
@router.post("/api/platforms/{name}/command")
async def api_platform_command(name: str, request: Request):
    user = deps.require_user(request)
    if name not in PLATFORMS:
        raise HTTPException(400, "未知平台")
    body = await request.json()
    cmd = body.get("cmd", "")
    if cmd not in _COMMANDS:
        raise HTTPException(400, f"不支持的命令: {cmd}")
    commands.write_command(name, cmd, body.get("payload") or {}, username=user["username"])
    security.log().info(f"[{user['username']}] 下发命令 {cmd} → {name}")
    return {"ok": True, "platform": name, "cmd": cmd}


@router.get("/api/platforms/{name}/pending")
async def api_platform_pending(name: str, request: Request):
    deps.require_user(request)
    return {"pending": commands.get_pending(name)}


# ── 平台元数据（移动端动态渲染用；只含键名与显示名，不含任何密钥值） ──
@router.get("/api/platforms/meta")
async def api_platforms_meta(request: Request):
    deps.require_user(request)
    return {"items": [
        {
            "name": name,
            "display_name": meta.get("display_name", name),
            "keys": list(meta.get("keys", [])),
            "secret_keys": list(meta.get("secret_keys", [])),
        }
        for name, meta in config.PLATFORM_META.items()
    ]}


# ── 账号绑定（用户级，登录即可） ──
@router.get("/api/settings/platforms/{name}")
async def api_get_platform_binding(name: str, request: Request):
    """读取【当前用户】的平台绑定配置（密钥脱敏）。"""
    user = deps.require_user(request)
    if name not in PLATFORMS:
        raise HTTPException(400, "未知平台")
    b = auth.get_user_binding(user["username"], name)
    cfg = (b or {}).get("config", {}) or {}
    out = deps.mask_platform_config(name, cfg)
    out["enabled"] = bool((b or {}).get("enabled"))
    return {"platform": name, "config": out}


@router.post("/api/settings/platforms/{name}")
async def api_save_platform_binding(name: str, request: Request):
    """保存【当前用户】的平台绑定（白名单键，未提交的保留原值）。"""
    user = deps.require_user(request)
    if name not in PLATFORMS:
        raise HTTPException(400, "未知平台")
    body = await request.json()
    keys = allowed_keys(name)
    b = auth.get_user_binding(user["username"], name)
    updates = dict((b or {}).get("config", {}) or {})
    for k in keys:
        if k in body:
            updates[k] = str(body[k]).strip()
    enabled = bool(body.get("enabled", True))
    auth.save_user_binding(user["username"], name, updates, enabled=enabled)
    # worker 每 15 秒扫描绑定，自动接入/重建实例，无需重启
    return {"ok": True, "needs_restart": False}


@router.post("/api/settings/platforms/{name}/test")
async def api_test_platform_binding(name: str, request: Request):
    """测试【当前用户】的平台凭证能否获取 access_token（表单值优先，未填沿用已存）。"""
    user = deps.require_user(request)
    if name not in PLATFORMS:
        raise HTTPException(400, "未知平台")
    body = await request.json()
    keys = allowed_keys(name)
    b = auth.get_user_binding(user["username"], name)
    cfg = dict((b or {}).get("config", {}) or {})
    for k in keys:
        if body.get(k) is not None:
            cfg[k] = str(body[k]).strip()
    try:
        t = config.PLATFORM_META[name]["test"]
        if t.get("method", "POST") == "GET":
            resp = httpx.get(t["url"], params=t["params"](cfg), timeout=15)
        else:
            resp = httpx.post(t["url"], json=t["body"](cfg), timeout=15)
        data = resp.json()
        field = t["ok_field"]
        val = data.get(field, "")
        ok = bool(val)
        detail = (f"获取到 {field}（{len(str(val))} 字符）"
                  if ok else f"失败: {data.get('errmsg') or data.get('message') or resp.text[:150]}")
        return {"ok": ok, "detail": detail}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"网络错误: {e}"}
