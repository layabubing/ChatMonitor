"""账号级 AI 配置：每个账号自带 API Key / 模型 / @ 回复策略。

与全局（configs/app.env）的关系：
- `AI_API_KEY` 完全以账号为准；**账号未配置则不再回退全局**（AI 功能停用）。
- `base_url` / `model` 允许留空，留空时沿用全局默认（同一平台只换 Key/模型是常见场景）。
"""
from __future__ import annotations

import time

from core.accounts import db

DEFAULTS = {
    "base_url": "",
    "api_key": "",
    "model": "",
    "model_vision": "",
    "at_reply_enabled": False,
    "at_rate_limit": 5,          # 每群每分钟最多回复条数（0 = 不回复）
    "context_rounds": 0,         # 多轮上下文轮数（0 = 单轮）
    "report_push_enabled": False,
    "report_push_group": "",     # 日报推送目标群 openid（空 = 不推）
}

_FIELDS = ("base_url", "api_key", "model", "model_vision", "at_reply_enabled",
           "at_rate_limit", "context_rounds", "report_push_enabled", "report_push_group")


def get_user_ai(username: str) -> dict:
    """读取账号 AI 配置。`api_key` 为明文（仅供 worker 内部使用，Web 层必须脱敏）。"""
    username = (username or "").strip()
    if not username:
        return dict(DEFAULTS)
    with db.connect() as conn:
        row = conn.execute(
            "SELECT base_url, api_key, model, model_vision, at_reply_enabled, "
            "at_rate_limit, context_rounds, report_push_enabled, report_push_group "
            "FROM user_ai WHERE username=?", (username,)).fetchone()
    if not row:
        return dict(DEFAULTS)
    return {
        "base_url": row["base_url"] or "",
        "api_key": row["api_key"] or "",
        "model": row["model"] or "",
        "model_vision": row["model_vision"] or "",
        "at_reply_enabled": bool(row["at_reply_enabled"]),
        "at_rate_limit": int(row["at_rate_limit"] or 0),
        "context_rounds": int(row["context_rounds"] or 0),
        "report_push_enabled": bool(row["report_push_enabled"]),
        "report_push_group": row["report_push_group"] or "",
    }


def save_user_ai(username: str, **fields) -> dict:
    """部分更新账号 AI 配置（未传的字段保留原值）；返回保存后的完整配置。"""
    cur = get_user_ai(username)
    for k in _FIELDS:
        if k in fields and fields[k] is not None:
            cur[k] = fields[k]
    # 规范化：限流 0-60 条/分钟，上下文 0-20 轮
    try:
        cur["at_rate_limit"] = max(0, min(60, int(cur["at_rate_limit"] or 0)))
    except (TypeError, ValueError):
        cur["at_rate_limit"] = 0
    try:
        cur["context_rounds"] = max(0, min(20, int(cur["context_rounds"] or 0)))
    except (TypeError, ValueError):
        cur["context_rounds"] = 0
    now = int(time.time() * 1000)
    with db.lock, db.connect() as conn:
        conn.execute(
            """INSERT INTO user_ai (username, base_url, api_key, model, model_vision,
                   at_reply_enabled, at_rate_limit, context_rounds,
                   report_push_enabled, report_push_group, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(username) DO UPDATE SET
                   base_url=excluded.base_url,
                   api_key=excluded.api_key,
                   model=excluded.model,
                   model_vision=excluded.model_vision,
                   at_reply_enabled=excluded.at_reply_enabled,
                   at_rate_limit=excluded.at_rate_limit,
                   context_rounds=excluded.context_rounds,
                   report_push_enabled=excluded.report_push_enabled,
                   report_push_group=excluded.report_push_group,
                   updated_at=excluded.updated_at""",
            (username, cur["base_url"], cur["api_key"], cur["model"], cur["model_vision"],
             1 if cur["at_reply_enabled"] else 0, cur["at_rate_limit"], cur["context_rounds"],
             1 if cur["report_push_enabled"] else 0, cur["report_push_group"], now),
        )
        conn.commit()
    return cur


def ai_overrides(username: str) -> dict:
    """生成注入 worker config 的覆盖项（供 main._collect_instances 使用）。

    规则：
    - `AI_API_KEY` 一律以账号为准；**账号无 Key 时显式清空**，使 AI 功能停用而不回退全局。
    - `base_url` / `model` / `model_vision` 留空则不覆盖（沿用全局默认）。
    """
    u = get_user_ai(username)
    if not u["api_key"]:
        return {
            "AI_API_KEY": "",
            "AI_AT_REPLY": "false", "AI_AT_RATE": "0", "AI_CTX_ROUNDS": "0",
            "AI_REPORT_PUSH": "false", "AI_REPORT_GROUP": "",
        }
    out = {
        "AI_API_KEY": u["api_key"],
        "AI_AT_REPLY": "true" if u["at_reply_enabled"] else "false",
        "AI_AT_RATE": str(u["at_rate_limit"]),
        "AI_CTX_ROUNDS": str(u["context_rounds"]),
        "AI_REPORT_PUSH": "true" if u["report_push_enabled"] else "false",
        "AI_REPORT_GROUP": u["report_push_group"],
    }
    if u["base_url"]:
        out["AI_BASE_URL"] = u["base_url"]
    if u["model"]:
        out["AI_MODEL"] = u["model"]
    if u["model_vision"] or u["model"]:
        out["AI_MODEL_VISION"] = u["model_vision"] or u["model"]
    return out
