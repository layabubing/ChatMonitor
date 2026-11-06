"""Shared subscription routing for callbacks and pre-upgrade file inboxes."""
from __future__ import annotations

import json

import config
from core import accounts, delivery


def subscriptions() -> list[dict]:
    out = []
    global_config = config.get_platform_config("workwechat")
    if global_config.get("WORKWECHAT_ENABLED") == "true":
        out.append({**global_config, "recipient": ""})
    for user in accounts.list_bound_users("workwechat"):
        out.append({**global_config, **user["config"], "recipient": user["username"]})
    return out


def recipients(message: dict, candidates: list[dict]) -> list[str]:
    return list({cfg["recipient"] for cfg in candidates
                 if cfg.get("WORKWECHAT_CORP_ID") == message.get("corpid")
                 and str(cfg.get("WORKWECHAT_AGENT_ID", "")) == str(message.get("agent_id", ""))})


def migrate_legacy() -> None:
    """Import pending legacy files without destructively popping another app's data.

    Unmatched/invalid files stay on disk for investigation. Duplicate concurrent
    imports are harmless because delivery identities are unique.
    """
    candidates = subscriptions()
    root = config.DATA_DIR / "inbox" / "workwechat"
    for path in (*root.glob("*.json"), *root.glob("*/*.json")):
        try:
            message = json.loads(path.read_text(encoding="utf-8"))
            targets = recipients(message, candidates)
            if targets and delivery.enqueue("workwechat", message, targets):
                path.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError):
            # Leave the file intact; an unsuccessful import must not lose data.
            continue
