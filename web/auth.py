"""
Web 认证层：JWT + HttpOnly Cookie（密码/用户/绑定/关键词的持久化下沉到 core.accounts）。
- 令牌携带 password_version，改密/删号后旧 token 自动失效
- 首个 admin 由 app.env 的 ADMIN_USERNAME/PASSWORD 自动种子创建
- 本模块只做「认证」，数据访问统一走 core.accounts（消除 web↔core 循环依赖）

为兼容既有调用方，本模块 re-export 了 core.accounts 的用户/绑定/关键词函数。
"""
from __future__ import annotations

import hmac
import secrets
import time

import jwt
from fastapi import Request, Response

from config import get_app_config
from core import accounts

# ── re-export：数据访问统一入口（既有代码/测试仍可 auth.xxx 调用） ──
from core.accounts import (  # noqa: F401
    count_users,
    create_user,
    ensure_admin,
    find_user,
    get_user_binding,
    get_user_keywords,
    hash_password,
    list_bound_users,
    list_users,
    save_user_binding,
    save_user_keywords,
    set_store_path,
    update_nickname,
    update_password,
    verify_password,
)

COOKIE_NAME = "chat_monitor_token"
TOKEN_TTL = 7 * 24 * 3600  # 7 天

_ROLE_ADMIN = accounts.ROLE_ADMIN
_ROLE_USER = accounts.ROLE_USER


# ═══════════════ 令牌 ═══════════════
def _config() -> dict:
    return get_app_config()


def create_token(username: str, role: str) -> str:
    """签发 token：携带密码版本号（改密后旧 token 自动失效）。"""
    user = find_user(username)
    pvv = user["password_version"] if user else 1
    payload = {"sub": username, "role": role, "pvv": pvv,
               "iat": int(time.time()), "exp": int(time.time()) + TOKEN_TTL}
    return jwt.encode(payload, _config()["JWT_SECRET"], algorithm="HS256")


def verify_token(token: str) -> dict | None:
    """校验 token：签名 + 用户存在性 + 密码版本一致性（支持改密/删号后失效）。"""
    try:
        payload = jwt.decode(token, _config()["JWT_SECRET"], algorithms=["HS256"])
        username = payload.get("sub")
        if not username:
            return None
        user = find_user(username)
        if not user:
            return None   # 用户已删除 → token 失效
        if payload.get("pvv", 1) != user["password_version"]:
            return None   # 改密后 → 旧 token 失效
        return {
            "username": username,
            "role": payload.get("role", _ROLE_USER),
            "nickname": user["nickname"] or "",
        }
    except Exception:  # noqa: BLE001
        return None


def check_login(request: Request) -> dict | None:
    """返回 {username, role, nickname} 或 None。"""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        # 移动端回退：Authorization: Bearer <jwt>（网页端仍走 Cookie）
        authz = request.headers.get("authorization", "")
        if authz.lower().startswith("bearer "):
            token = authz[7:].strip()
    return verify_token(token) if token else None


def require_login(request: Request) -> dict:
    user = check_login(request)
    if not user:
        raise PermissionError("未登录")
    return user


def require_admin(request: Request) -> dict:
    user = require_login(request)
    if user["role"] != _ROLE_ADMIN:
        raise PermissionError("需要管理员权限")
    return user


# ═══════════════ 登录/注册 ═══════════════
def do_login(username: str, password: str) -> str | None:
    """校验账号密码，成功返回 token。"""
    user = find_user((username or "").strip())
    if not user or not verify_password(user["username"], password):
        return None
    return create_token(user["username"], user["role"])


def register(username: str, password: str) -> tuple[bool, str]:
    """开放注册：默认普通用户。"""
    return create_user(username, password, _ROLE_USER)


# ═══════════════ Cookie ═══════════════
def set_auth_cookie(response: Response, token: str) -> None:
    secure = _config().get("COOKIE_SECURE", "false") == "true"
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax",
                        secure=secure, max_age=TOKEN_TTL)


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)


# ═══════════════ 启动加固 ═══════════════
_DEFAULT_SECRETS = ("", "change-me-to-a-long-random-secret")


def ensure_secure_secret() -> None:
    """JWT_SECRET 若为默认/空值则自动生成随机密钥写入 app.env（旧会话将失效）。"""
    from config import CONFIGS_DIR
    if _config().get("JWT_SECRET", "") not in _DEFAULT_SECRETS:
        return
    new_secret = secrets.token_hex(32)
    path = CONFIGS_DIR / "app.env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out = [line for line in lines if not line.startswith("JWT_SECRET=")]
    out.append(f"JWT_SECRET={new_secret}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("[auth] ⚠ 检测到默认 JWT_SECRET，已自动生成随机密钥（旧登录会话失效）")


def warn_default_password() -> None:
    """启动时检测 admin 是否仍为默认密码，给出醒目警告。"""
    try:
        cfg = get_app_config()
        admin = find_user(cfg.get("ADMIN_USERNAME", "admin"))
        if admin and hmac.compare_digest(
                hash_password("change-me-please", admin["salt"]), admin["password_hash"]):
            print("\n" + "!" * 56)
            print("⚠  警告：管理员账号仍在使用默认密码 change-me-please！")
            print("   公开部署前请立即在「设置」中修改密码。")
            print("!" * 56 + "\n")
    except Exception:  # noqa: BLE001
        pass
