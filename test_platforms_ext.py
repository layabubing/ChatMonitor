"""
平台扩展回归测试（飞书 + 企业微信，不依赖真实平台账号）
验证: 注册表工厂 → 飞书消息解析 → 企微加解密(官方算法) → 收件箱 → 企微回调端点端到端 → 适配器路由匹配
运行: ./.venv/Scripts/python.exe test_platforms_ext.py
"""
from __future__ import annotations

import os
import random
import string
import sys
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def _fresh_aes_key(seed: int) -> str:
    random.seed(seed)
    return "".join(random.choices(string.ascii_letters + string.digits, k=43))


def main():
    print("══ 1. PLATFORM_META 注册表 ══")
    import config
    check("注册表含 4 平台", set(config.PLATFORMS) == {"qq", "dingtalk", "feishu", "workwechat"},
          str(config.PLATFORMS))
    check("feishu 凭证键", config.PLATFORM_META["feishu"]["app_id_key"] == "FEISHU_APP_ID")
    check("workwechat 凭证键", config.PLATFORM_META["workwechat"]["app_id_key"] == "WORKWECHAT_CORP_ID")

    from core.adapter import PlatformAdapter
    f = PlatformAdapter.create("feishu", {"FEISHU_APP_ID": "x", "FEISHU_APP_SECRET": "y", "FEISHU_CHAT_IDS": "oc_a,oc_b"})
    check("工厂创建 feishu", type(f).__name__ == "FeishuAdapter")
    check("飞书群过滤", f._group_filter == {"oc_a", "oc_b"})
    w = PlatformAdapter.create("workwechat", {"WORKWECHAT_CORP_ID": "ww1", "WORKWECHAT_AGENT_ID": "1000002"})
    check("工厂创建 workwechat", type(w).__name__ == "WorkWechatAdapter" and w._agent_id == "1000002")

    print("══ 2. 飞书消息解析 ══")
    from platforms.feishu import _parse_content
    text, mtype, media = _parse_content({"msg_type": "text", "content": '{"text":"你好飞书"}'})
    check("text 解析", text == "你好飞书" and mtype == "text")
    text, mtype, media = _parse_content({"msg_type": "image", "content": '{"image_key":"img_1"}'})
    check("image 解析", mtype == "image" and media[0]["file_key"] == "img_1")
    text, mtype, _ = _parse_content({"msg_type": "post",
                                     "content": '{"title":"t","content":[[{"tag":"text","text":"a"},{"tag":"a","text":"链","href":"http://x"}]]}'})
    check("post 富文本提取", text == "a 链(http://x)" and mtype == "text", text)
    text, mtype, media = _parse_content({"msg_type": "audio", "content": '{"file_key":"f1"}'})
    check("audio 解析", mtype == "audio" and media[0]["file_key"] == "f1")

    print("══ 3. 企业微信加解密（官方算法往返） ══")
    from web.wxmsgcrypt import WXBizMsgCrypt, WXBizMsgCryptError
    aes_key = _fresh_aes_key(42)
    token, corp_id = "QDG6eK", "wx5823bf96d3bd56c7"
    c = WXBizMsgCrypt(token, aes_key, corp_id)
    xml = (f"<xml><ToUserName><![CDATA[{corp_id}]]></ToUserName>"
           "<FromUserName><![CDATA[zhangsan]]></FromUserName>"
           "<CreateTime>1348831860</CreateTime><MsgType><![CDATA[text]]></MsgType>"
           "<Content><![CDATA[你好，测试]]></Content><MsgId>1234567890</MsgId>"
           "<AgentID>1000002</AgentID><ChatId><![CDATA[wr_test123]]></ChatId></xml>")
    enc = c.encrypt(xml)
    ts, nonce = str(int(time.time())), "1757997317"
    sig = c.signature(ts, nonce, enc)
    check("验签通过", c.verify(sig, ts, nonce, enc))
    outer = f"<xml><ToUserName><![CDATA[{corp_id}]]></ToUserName><Encrypt><![CDATA[{enc}]]></Encrypt></xml>"
    msg = c.decrypt_message(outer, sig, ts, nonce)
    check("解密往返", msg.get("Content") == "你好，测试" and msg.get("ChatId") == "wr_test123"
          and msg.get("MsgId") == "1234567890", str(msg))
    try:
        c.decrypt_message(outer, "bad" + sig[3:], ts, nonce)
        check("错误签名拦截", False)
    except WXBizMsgCryptError:
        check("错误签名拦截", True)
    try:
        c.decrypt_message("<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><xml><Encrypt>x</Encrypt></xml>",
                          sig, ts, nonce)
        check("XXE 防护", False)
    except WXBizMsgCryptError:
        check("XXE 防护", True)
    try:
        WXBizMsgCrypt(token, "short", corp_id)
        check("AESKey 长度校验", False)
    except WXBizMsgCryptError:
        check("AESKey 长度校验", True)

    print("══ 4. 收件箱（跨进程消息通道 + 多租户 scope 隔离） ══")
    tmp = Path(tempfile.mkdtemp(prefix="chatmon_ext_"))
    config.DATA_DIR = tmp
    from core import inbox
    check("push 消息", inbox.push_message("workwechat", {"msg_id": "workwechat_1", "content": "hi"}))
    check("push 第二条", inbox.push_message("workwechat", {"msg_id": "workwechat_2", "content": "hello"}))
    got = inbox.pop_messages("workwechat")
    check("pop 两条", len(got) == 2 and {m["msg_id"] for m in got} == {"workwechat_1", "workwechat_2"})
    check("消费后清空", inbox.pop_messages("workwechat") == [])
    check("无 msg_id 拒绝", not inbox.push_message("workwechat", {"content": "x"}))
    # 多租户 scope 隔离：不同 corpid 消息落入各自子目录，互不干扰（S1 竞态修复）
    inbox.push_message("workwechat", {"msg_id": "ww_a_1", "corpid": "corpA", "content": "A"})
    inbox.push_message("workwechat", {"msg_id": "ww_b_1", "corpid": "corpB", "content": "B"})
    check("scope=corpA 只拿 A", [m["msg_id"] for m in inbox.pop_messages("workwechat", scope="corpA")] == ["ww_a_1"])
    check("scope=corpB 只拿 B", [m["msg_id"] for m in inbox.pop_messages("workwechat", scope="corpB")] == ["ww_b_1"])
    check("根目录无残留", inbox.pop_messages("workwechat") == [])

    print("══ 5. 企业微信回调端点端到端 ══")
    from fastapi.testclient import TestClient
    import web.server
    client = TestClient(web.server.app)
    from core import accounts
    accounts.save_user_binding("admin", "workwechat", {
        "WORKWECHAT_CORP_ID": corp_id, "WORKWECHAT_AGENT_ID": "1000002",
        "WORKWECHAT_SECRET": "s", "WORKWECHAT_TOKEN": token,
        "WORKWECHAT_AES_KEY": aes_key, "WORKWECHAT_ENABLED": "true",
    }, enabled=True)
    # URL 验证
    echostr = "echo_hello_world_123456"
    enc_echo = c.encrypt(echostr)
    sig_echo = c.signature(ts, nonce, enc_echo)
    r = client.get("/api/workwechat/callback", params={
        "msg_signature": sig_echo, "timestamp": ts, "nonce": nonce, "echostr": enc_echo})
    check("GET 验证返回 echostr", r.status_code == 200 and r.text == echostr, r.text)
    r2 = client.get("/api/workwechat/callback", params={
        "msg_signature": "bad" + sig_echo[3:], "timestamp": ts, "nonce": nonce, "echostr": enc_echo})
    check("错误签名 GET 403", r2.status_code == 403, str(r2.status_code))
    # 消息推送
    enc_msg = c.encrypt(xml)
    sig_msg = c.signature(ts, nonce, enc_msg)
    outer2 = f"<xml><ToUserName><![CDATA[{corp_id}]]></ToUserName><Encrypt><![CDATA[{enc_msg}]]></Encrypt></xml>"
    r3 = client.post("/api/workwechat/callback", params={
        "msg_signature": sig_msg, "timestamp": ts, "nonce": nonce},
        content=outer2.encode("utf-8"), headers={"Content-Type": "text/xml"})
    check("POST 接收 success", r3.status_code == 200 and r3.text == "success", r3.text)
    # 回调推送带 corpid（ToUserName）→ 落入对应子目录，需按 scope 消费
    msgs = inbox.pop_messages("workwechat", scope=corp_id)
    check("收件箱落盘(按 corpid scope)", len(msgs) == 1 and msgs[0]["msg_id"] == "workwechat_1234567890"
          and msgs[0]["chat_id"] == "wr_test123" and msgs[0]["content"] == "你好，测试", str(msgs))
    # 限流验证：连续错误签名触发 429
    r429 = None
    for _ in range(35):
        r429 = client.get("/api/workwechat/callback", params={
            "msg_signature": "bad", "timestamp": ts, "nonce": nonce, "echostr": enc_echo})
    check("连续失败触发限流 429", r429.status_code == 429, str(r429.status_code))

    print("══ 6. 企微适配器路由匹配（多租户隔离） ══")
    ad = PlatformAdapter.create("workwechat", {
        "WORKWECHAT_CORP_ID": corp_id, "WORKWECHAT_AGENT_ID": "1000002", "WORKWECHAT_SECRET": "s"})
    raw = {"msg_id": "workwechat_9", "corpid": corp_id, "agent_id": "1000002",
           "chat_id": "wr_a", "sender": "u1", "content": "测试文本",
           "msg_type": "text", "media_ids": [], "ts": 1000}
    cm = ad._to_chatmessage(raw)
    check("匹配实例转换", cm is not None and cm.content == "测试文本" and cm.group_id == "wr_a"
          and cm.ts == 1000)
    check("跨企业过滤", ad._to_chatmessage(dict(raw, corpid="other_corp")) is None)
    check("跨应用过滤", ad._to_chatmessage(dict(raw, agent_id="999")) is None)
    check("群过滤", ad._to_chatmessage(dict(raw, chat_id="not_in_filter")) is not None)  # 未配置群过滤=全部

    print(f"\n══ 结果: {PASS} 通过 / {FAIL} 失败 ══")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
