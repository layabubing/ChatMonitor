"""账号级 AI 配置接口：每个账号自带 API Key / 模型 / @ 回复策略 / 日报推送。

配套仓储：core/accounts/ai.py（get_user_ai / save_user_ai / ai_overrides）
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

import config
from core import accounts
from web import deps, security

router = APIRouter()

# 允许前端写入的字段（白名单，防止越权写 DB 列）
_WRITABLE = ("base_url", "api_key", "model", "model_vision", "at_reply_enabled",
             "at_rate_limit", "context_rounds", "report_push_enabled", "report_push_group")


@router.get("/api/settings/ai")
async def api_get_ai(request: Request):
    """当前账号的 AI 配置（api_key 脱敏，仅回显是否已配置）。"""
    user = deps.require_user(request)
    u = accounts.get_user_ai(user["username"])
    g = config.get_app_config()
    return {
        "base_url": u["base_url"],
        "model": u["model"],
        "model_vision": u["model_vision"],
        "at_reply_enabled": u["at_reply_enabled"],
        "at_rate_limit": u["at_rate_limit"],
        "context_rounds": u["context_rounds"],
        "report_push_enabled": u["report_push_enabled"],
        "report_push_group": u["report_push_group"],
        "key_set": bool(u["api_key"]),
        "key_masked": deps.mask(u["api_key"]),
        # 全局默认值：仅作输入框占位提示，不参与本账号运行
        "global_defaults": {
            "base_url": g.get("AI_BASE_URL", ""),
            "model": g.get("AI_MODEL", ""),
            "model_vision": g.get("AI_MODEL_VISION", ""),
        },
    }


@router.post("/api/settings/ai")
async def api_save_ai(request: Request):
    """保存账号 AI 配置（部分更新；`api_key` 传空串表示清空 → AI 功能停用）。"""
    user = deps.require_user(request)
    body = await request.json()
    fields: dict = {}
    for k in _WRITABLE:
        if k not in body:
            continue
        v = body[k]
        if k in ("at_reply_enabled", "report_push_enabled"):
            fields[k] = str(v).strip().lower() in ("1", "true", "yes", "on")
        elif k in ("at_rate_limit", "context_rounds"):
            try:
                fields[k] = int(v)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{k} 必须是整数") from None
        else:
            fields[k] = str(v or "").strip()
    url = fields.get("base_url", "")
    if url and not url.startswith(("http://", "https://")):
        raise HTTPException(400, "base_url 需以 http:// 或 https:// 开头")
    saved = accounts.save_user_ai(user["username"], **fields)
    security.log().info(f"[{user['username']}] 更新 AI 配置（key_set={bool(saved['api_key'])}）")
    return {"ok": True, "key_set": bool(saved["api_key"]), "needs_restart": False,
            "note": "worker 每 15 秒重扫绑定，配置约 15 秒内自动生效"}


@router.post("/api/settings/ai/test")
async def api_test_ai(request: Request):
    """用账号自己的凭证做一次最小调用验证；支持用表单里未保存的值直接测试。"""
    user = deps.require_user(request)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001  空 body 也允许（用已保存配置测试）
        body = {}
    u = accounts.get_user_ai(user["username"])
    g = config.get_app_config()
    key = str(body.get("api_key") or u["api_key"] or "").strip()
    base = str(body.get("base_url") or u["base_url"] or g.get("AI_BASE_URL", "")).strip().rstrip("/")
    model = str(body.get("model") or u["model"] or g.get("AI_MODEL", "")).strip()
    if not key:
        return {"ok": False, "detail": "尚未填写 API Key（未配置时不会回退到全局凭据）"}
    if not base or not model:
        return {"ok": False, "detail": "base_url 或 model 为空"}
    try:
        with httpx.Client(timeout=20) as c:
            r = c.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model,
                      "messages": [{"role": "user", "content": "只回复两个字母：OK"}],
                      "max_tokens": 16},
            )
        if r.status_code == 200:
            txt = ((((r.json().get("choices") or [{}])[0].get("message")) or {}).get("content") or "").strip()
            return {"ok": True, "detail": f"调用成功（模型返回：{txt[:20] or '空'}）"}
        return {"ok": False, "detail": f"HTTP {r.status_code}: {r.text[:150]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"网络错误: {e}"}
