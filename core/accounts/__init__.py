"""
账户/租户持久化层（业务层，位于 core，不依赖 web）。
包含三个仓储：用户、平台绑定、用户关键词，共享同一 users.db。

web/auth.py 在此之上实现 JWT/Cookie 认证；worker（core.pipeline / main）
直接使用本层读取租户绑定与关键词，从而消除 core → web 的反向依赖。
"""
from __future__ import annotations

from core.accounts.bindings import get_user_binding, list_bound_users, save_user_binding
from core.accounts.db import connect, hash_password, set_store_path, store_path
from core.accounts.keywords import flatten, get_user_keywords, save_user_keywords
from core.accounts.users import (
    ROLE_ADMIN,
    ROLE_USER,
    SALT_DEFAULT,
    count_users,
    create_user,
    ensure_admin,
    find_user,
    list_users,
    update_nickname,
    update_password,
    verify_password,
)

__all__ = [
    "connect", "hash_password", "set_store_path", "store_path",
    "ROLE_ADMIN", "ROLE_USER", "SALT_DEFAULT",
    "create_user", "find_user", "ensure_admin", "count_users", "list_users",
    "update_password", "update_nickname", "verify_password",
    "get_user_binding", "save_user_binding", "list_bound_users",
    "get_user_keywords", "save_user_keywords", "flatten",
]
