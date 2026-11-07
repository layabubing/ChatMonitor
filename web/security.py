"""
Web 安全横切关注点：审计日志、登录限流（防暴力破解）、注册频控、CSRF 防护。
从路由逻辑中剥离，供各 router 复用。
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

import config

# ── 限流参数 ──
MAX_FAILS = 5          # 窗口内最大失败次数
WINDOW_SEC = 300       # 窗口 5 分钟
LOCK_SEC = 600         # 锁定 10 分钟
REGISTER_WINDOW_SEC = 600   # 注册频控窗口 10 分钟
REGISTER_MAX = 5            # 同 IP 窗口内最多注册次数

_fail_map: dict[str, deque] = defaultdict(deque)
_locked_until: dict[str, float] = {}


# ── 审计日志（logs/web.log；延迟初始化避免导入即占锁/测试互斥） ──
def log() -> logging.Logger:
    lg = logging.getLogger("web")
    if not lg.handlers:
        try:
            config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
            h = logging.FileHandler(str(config.LOGS_DIR / "web.log"), encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            lg.addHandler(h)
            lg.setLevel(logging.INFO)
        except Exception:  # noqa: BLE001  日志失败不影响服务
            logging.basicConfig(level=logging.INFO,
                                format="%(asctime)s [%(levelname)s] %(message)s")
    return lg


def client_ip(request: Request) -> str:
    """取客户端真实 IP：优先 Nginx 设置的 X-Real-IP（不可伪造），其次 TCP 直连地址；
    不信任客户端可控的 X-Forwarded-For 原始值。"""
    xri = request.headers.get("x-real-ip", "").strip()
    if xri:
        return xri
    return request.client.host if request.client else "unknown"


# ── 登录限流 ──
def login_locked(key: str) -> int:
    """返回剩余锁定秒数（0=未锁定）。"""
    remain = _locked_until.get(key, 0.0) - time.time()
    return int(remain) if remain > 0 else 0


def record_login_fail(key: str) -> int:
    """记录一次失败；触发锁定时返回锁定秒数。"""
    now = time.time()
    # 惰性清理过期项（防止内存无限增长）
    if len(_fail_map) > 500:
        for k in list(_fail_map):
            q = _fail_map[k]
            while q and now - q[0] > WINDOW_SEC:
                q.popleft()
            if not q:
                _fail_map.pop(k, None)
                _locked_until.pop(k, None)
    q = _fail_map[key]
    q.append(now)
    while q and now - q[0] > WINDOW_SEC:
        q.popleft()
    if len(q) >= MAX_FAILS:
        _locked_until[key] = now + LOCK_SEC
        return LOCK_SEC
    return 0


def clear_login_fails(key: str) -> None:
    _fail_map.pop(key, None)
    _locked_until.pop(key, None)


# ── 注册频控（同 IP 窗口内限次，防批量注册） ──
def register_throttled(ip: str) -> bool:
    now = time.time()
    q = _fail_map.get(f"reg:{ip}")
    if not q:
        return False
    while q and now - q[0] > REGISTER_WINDOW_SEC:
        q.popleft()
    return len(q) >= REGISTER_MAX


def record_register(ip: str) -> None:
    _fail_map.setdefault(f"reg:{ip}", deque()).append(time.time())


# ── CSRF 防护：非 GET 请求校验 Origin（同源才放行） ──
async def csrf_guard(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin:
            host = request.headers.get("host", "")
            if origin not in (f"http://{host}", f"https://{host}"):
                return JSONResponse({"error": "跨站请求被拒绝"}, status_code=403)
        else:
            # 无 Origin 的写请求（部分客户端/旧浏览器）：改用 Referer 兜底校验。
            # 两者都缺失时放行（Cookie 已设 SameSite=lax，跨站 POST 不会携带凭据）。
            referer = request.headers.get("referer")
            if referer:
                host = request.headers.get("host", "")
                if not (referer.startswith(f"http://{host}/") or referer.startswith(f"https://{host}/")):
                    return JSONResponse({"error": "跨站请求被拒绝"}, status_code=403)
    return await call_next(request)


# ── 安全响应头：防 MIME 嗅探 / 点击劫持 / 降低信息泄露 ──
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # 禁止浏览器猜测 Content-Type（避免上传内容被当脚本执行）
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    # 禁止被第三方站点嵌入（同源 iframe 仍可用，日报预览依赖它）
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    # 跨域跳转时隐藏完整路径
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # 关闭不需要的浏览器能力
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    # 仅 HTTPS 下发 HSTS（HTTP 环境下发会让浏览器强制升级，可能导致本地调试失败）
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").lower()
    if proto == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response
