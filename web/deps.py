"""
Web 共享依赖：多租户 Storage 获取、运行状态判断、鉴权辅助、分页/脱敏、报告文件解析。
供各 router 复用，避免逻辑散落在路由函数里。
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import HTTPException, Request

import config
from config import DATA_DIR, PLATFORMS, get_platform_config
from core import accounts
from core.storage import Storage
from web import auth

_storage_cache: dict[str, Storage] = {}


def storage(platform: str, username: str = "") -> Storage:
    """多租户：username 指定时返回该用户的独立 Storage，否则全局（旧数据兼容）。"""
    key = f"{username}|{platform}" if username else platform
    if key not in _storage_cache:
        if username:
            config.ensure_user_dirs(username)
            _storage_cache[key] = Storage(config.user_platform_db_path(username, platform))
        else:
            _storage_cache[key] = Storage(config.platform_db_path(platform))
    return _storage_cache[key]


def is_alive(platform: str, username: str = "") -> bool:
    """通过 alive 心跳文件判断 worker 是否在运行（多租户，见原逻辑注释）。"""
    global_cfg = get_platform_config(platform)
    global_enabled = global_cfg.get(f"{platform.upper()}_ENABLED", "false") == "true"
    global_id = global_cfg.get("QQ_APP_ID" if platform == "qq" else "DINGTALK_APP_KEY", "")
    if username:
        b = accounts.get_user_binding(username, platform)
        if not b or not b.get("enabled"):
            return False   # 未绑定/未启用 → 未运行
        user_id = (b.get("config") or {}).get(
            "QQ_APP_ID" if platform == "qq" else "DINGTALK_APP_KEY", "")
        # 仅当全局启用 且 凭证与全局相同 → 共享全局实例；否则用户独立实例
        if global_enabled and user_id and user_id == global_id:
            p = DATA_DIR / f"{platform}.alive"
        else:
            p = config.user_data_dir(username) / f"{platform}.alive"
    else:
        p = DATA_DIR / f"{platform}.alive"
    if not p.exists():
        return False
    try:
        ts = int(p.read_text().strip())
        return time.time() - ts < 120
    except Exception:  # noqa: BLE001
        return False


# ── 鉴权辅助 ──
def require_user(request: Request) -> dict:
    """登录即可；未登录 401。"""
    try:
        return auth.require_login(request)
    except PermissionError:
        raise HTTPException(401, "未登录")


def require_admin(request: Request) -> dict:
    """需要管理员；未登录 401，普通用户 403。"""
    try:
        return auth.require_admin(request)
    except PermissionError as e:
        raise HTTPException(403, str(e))


# ── 分页/脱敏 ──
def page_size(n: int) -> int:
    """分页大小上限（防超大查询 DoS）。"""
    return min(max(1, int(n)), 200)


def mask(text: str) -> str:
    t = text or ""
    return t[:4] + "*" * 6 + t[-4:] if len(t) > 12 else "******"


def mask_platform_config(name: str, cfg: dict) -> dict:
    """平台配置脱敏返回（密钥只回显掩码）。"""
    out = {}
    for k in ("QQ_APP_ID", "QQ_APP_SECRET", "QQ_ENV", "QQ_GROUP_OPENIDS", "QQ_ENABLED",
              "DINGTALK_APP_KEY", "DINGTALK_APP_SECRET", "DINGTALK_CHAT_IDS", "DINGTALK_ENABLED"):
        v = cfg.get(k, "")
        if k in ("QQ_APP_SECRET", "DINGTALK_APP_SECRET"):
            out[k] = mask(v)
            out[k + "_SET"] = bool(v)
        else:
            out[k] = v
    return out


# ── 报告 ──
def validate_report(platform: str, date: str) -> None:
    """防路径穿越：严格校验 platform 与 date 格式。"""
    if platform not in PLATFORMS or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise HTTPException(400, "非法参数")


def resolve_report_file(platform: str, date: str, user: dict, kind: str) -> Path:
    """解析某日报文件的真实路径（kind='html'|'docx'），带路径穿越防护与旧数据兼容。"""
    from config import REPORTS_DIR, platform_report_dir, user_data_dir, user_report_dir
    suffix = ".html" if kind == "html" else ".docx"
    db_field = "html_path" if kind == "html" else "docx_path"
    username = user["username"]
    # 1. 优先用数据库记录里的真实路径（兼容历史数据/路径迁移/旧版全局 reports）
    try:
        for r in storage(platform, username).query_reports(platform):
            if r["date"] == date and r.get(db_field):
                p = Path(r[db_field])
                allowed = [str(user_data_dir(username)), str(REPORTS_DIR)]
                if any(str(p).startswith(a) for a in allowed) and p.exists():
                    return p
    except Exception:  # noqa: BLE001
        pass
    # 2. 回退：重构标准用户目录路径
    path = user_report_dir(username, platform) / f"{date}-日报{suffix}"
    if path.exists():
        return path
    # 3. 兼容旧版全局 reports/（admin 历史数据）
    legacy = platform_report_dir(platform) / f"{date}-日报{suffix}"
    if user["role"] == "admin" and legacy.exists():
        return legacy
    raise HTTPException(404, "报告不存在")
