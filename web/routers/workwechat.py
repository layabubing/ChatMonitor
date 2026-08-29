"""企业微信回调端点（URL 验证 + 消息接收 → 收件箱）
回调 URL 配置: https://你的域名/api/workwechat/callback
鉴权: 企微 msg_signature 验签（Token/EncodingAESKey/CorpID 来自绑定配置，多用户遍历匹配）
防护: 验签失败限流（60s 窗口），防无效请求打满加解密开销
"""
from __future__ import annotations

import time
from collections import deque

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

import config
from core import accounts, inbox
from web.wxmsgcrypt import WXBizMsgCrypt, WXBizMsgCryptError

router = APIRouter()

_CALLBACK_PATH = "/api/workwechat/callback"

# ── 失败限流：60 秒窗口内验签失败超过阈值 → 临时拒绝 ──
_FAIL_WINDOW = 60
_FAIL_MAX = 30
_fail_ts: deque = deque()


def _rate_limited() -> bool:
    now = time.time()
    while _fail_ts and now - _fail_ts[0] > _FAIL_WINDOW:
        _fail_ts.popleft()
    return len(_fail_ts) >= _FAIL_MAX


def _record_fail() -> None:
    _fail_ts.append(time.time())


def _reject() -> None:
    _record_fail()
    raise HTTPException(403, "企微回调验证失败")


def _candidate_configs() -> list[dict]:
    """候选解密配置：全局 workwechat.env + 所有启用绑定的用户（按 corpid 匹配）。"""
    out = []
    g = config.get_platform_config("workwechat")
    if g.get("WORKWECHAT_CORP_ID") and g.get("WORKWECHAT_TOKEN"):
        out.append({"scope": "global", **g})
    for u in accounts.list_bound_users("workwechat"):
        c = u["config"]
        if c.get("WORKWECHAT_CORP_ID") and c.get("WORKWECHAT_TOKEN"):
            out.append({"scope": u["username"], **c})
    return out


def _make_crypt(cfg: dict) -> WXBizMsgCrypt | None:
    try:
        return WXBizMsgCrypt(cfg.get("WORKWECHAT_TOKEN", ""),
                             cfg.get("WORKWECHAT_AES_KEY", ""),
                             cfg.get("WORKWECHAT_CORP_ID", ""))
    except WXBizMsgCryptError:
        return None


@router.get(_CALLBACK_PATH)
async def workwechat_verify(request: Request):
    """URL 验证：验签通过后返回解密后的 echostr 明文。"""
    p = request.query_params
    msg_signature = p.get("msg_signature", "")
    timestamp = p.get("timestamp", "")
    nonce = p.get("nonce", "")
    echostr = p.get("echostr", "")
    if _rate_limited():
        raise HTTPException(429, "回调请求过于频繁")
    for cfg in _candidate_configs():
        crypt = _make_crypt(cfg)
        if not crypt or not crypt.verify(msg_signature, timestamp, nonce, echostr):
            continue
        try:
            _fail_ts.clear()   # 验证成功 → 复位限流计数
            return PlainTextResponse(crypt.decrypt(echostr))
        except WXBizMsgCryptError:
            continue
    _reject()

@router.post(_CALLBACK_PATH)
async def workwechat_receive(request: Request):
    """接收企微推送消息：验签 + AES 解密 → 解析 → 写入收件箱（worker 轮询消费）。"""
    p = request.query_params
    msg_signature = p.get("msg_signature", "")
    timestamp = p.get("timestamp", "")
    nonce = p.get("nonce", "")
    try:
        body = (await request.body()).decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "请求体读取失败")
    if not body.strip():
        raise HTTPException(400, "空请求体")
    if _rate_limited():
        raise HTTPException(429, "回调请求过于频繁")

    for cfg in _candidate_configs():
        crypt = _make_crypt(cfg)
        if not crypt:
            continue
        try:
            msg = crypt.decrypt_message(body, msg_signature, timestamp, nonce)
        except WXBizMsgCryptError:
            continue
        msg_id = str(msg.get("MsgId", "") or "").strip()
        if not msg_id:
            # 事件类推送（subscribe 等）无 MsgId，忽略
            return PlainTextResponse("success")
        chat_id = (msg.get("ChatId") or "").strip() or (msg.get("FromUserName") or "").strip()
        # 媒体消息：只取 MediaId（worker 侧下载）；PicUrl/ThumbMediaId 非 media_id 不混入
        media_ids: list[str] = []
        if msg.get("MediaId"):
            media_ids.append(str(msg["MediaId"]).strip())
        push = {
            "msg_id": f"workwechat_{msg_id}",
            "platform": "workwechat",
            "corpid": msg.get("ToUserName", ""),
            "agent_id": str(msg.get("AgentID", "") or ""),
            "chat_id": chat_id,
            "group_name": chat_id[-8:] or "企业微信群",
            "sender": msg.get("FromUserName", ""),
            "content": msg.get("Content") or "",
            "msg_type": msg.get("MsgType", "text"),
            "media_ids": media_ids,
            "ts": int(msg.get("CreateTime", 0) or 0) * 1000,   # 秒 → 毫秒
        }
        # 文本以外的消息给个可读占位
        if push["msg_type"] != "text" and not push["content"]:
            push["content"] = f"[{push['msg_type']}]" if push["msg_type"] != "image" else "[图片]"
        inbox.push_message("workwechat", push)
        _fail_ts.clear()   # 消息接收成功 → 复位限流计数
        return PlainTextResponse("success")
    _reject()


__all__ = ["router"]
