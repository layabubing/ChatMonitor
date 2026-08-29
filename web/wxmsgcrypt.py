"""
企业微信回调加解密（WXBizMsgCrypt 官方算法实现）
- URL 验证: GET 回调带 msg_signature/timestamp/nonce/echostr → 验签 → AES 解密 → 返回明文
- 消息推送: POST XML（Encrypt 节点）→ 验签 → AES 解密 → 明文 XML → 业务解析
- 加密: 随机16字节 + 4字节网络序(明文长度) + 明文 + corp_id，AES-256-CBC，PKCS7 填充
依赖: pycryptodome
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import xml.etree.ElementTree as ET

from Crypto.Cipher import AES


class WXBizMsgCryptError(Exception):
    """企微回调加解密错误"""


def _parse_xml(text: str) -> dict:
    """安全解析 XML（拒绝 DTD/实体，防 XXE 与实体膨胀）。"""
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise WXBizMsgCryptError("XML 含非法声明")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise WXBizMsgCryptError(f"XML 解析失败: {e}") from e
    return {child.tag: (child.text or "") for child in root}


class WXBizMsgCrypt:
    """企业微信回调消息加解密（Token + EncodingAESKey + CorpID）。"""

    def __init__(self, token: str, aes_key: str, corp_id: str):
        self.token = token or ""
        self.corp_id = corp_id or ""
        key_raw = (aes_key or "").strip()
        if len(key_raw) != 43:
            raise WXBizMsgCryptError(f"EncodingAESKey 无效（需 43 位，当前 {len(key_raw)}）")
        try:
            self.key = base64.b64decode(key_raw + "=")
        except Exception as e:  # noqa: BLE001
            raise WXBizMsgCryptError(f"EncodingAESKey 无效: {e}") from e
        if len(self.key) != 32:
            raise WXBizMsgCryptError("EncodingAESKey 解码后长度非法")
        self.iv = self.key[:16]

    # ── 签名 ──
    def signature(self, timestamp: str, nonce: str, encrypt: str) -> str:
        """SHA1(sort([token, timestamp, nonce, encrypt]).join())"""
        items = sorted([self.token, timestamp, nonce, encrypt])
        return hashlib.sha1("".join(items).encode("utf-8")).hexdigest()

    def verify(self, msg_signature: str, timestamp: str, nonce: str, encrypt: str) -> bool:
        calc = self.signature(timestamp, nonce, encrypt)
        # 常量时间比较，防时序侧信道
        return bool(msg_signature) and hmac.compare_digest(calc, (msg_signature or "").lower())

    # ── 解密 ──
    def decrypt(self, encrypted: str) -> str:
        """解密企微密文 → 原始明文（去除随机头/长度前缀/corp_id 校验）。"""
        try:
            raw = base64.b64decode(encrypted)
        except Exception as e:  # noqa: BLE001
            raise WXBizMsgCryptError(f"Base64 解码失败: {e}") from e
        if len(raw) < 32 or len(raw) % 16 != 0:
            raise WXBizMsgCryptError("密文长度非法")
        plain = AES.new(self.key, AES.MODE_CBC, self.iv).decrypt(raw)
        # 去除 PKCS7 填充
        pad = plain[-1]
        if pad < 1 or pad > 32 or pad > len(plain):
            raise WXBizMsgCryptError("填充非法")
        plain = plain[:-pad]
        # 随机16字节 + 4字节网络序长度 + 明文 + receiveid
        if len(plain) < 20:
            raise WXBizMsgCryptError("明文长度非法")
        msg_len = struct.unpack(">I", plain[16:20])[0]
        msg = plain[20:20 + msg_len]
        receive_id = plain[20 + msg_len:].decode("utf-8", "ignore")
        if self.corp_id and receive_id and receive_id != self.corp_id:
            raise WXBizMsgCryptError(f"CorpID 不匹配: {receive_id}")
        return msg.decode("utf-8", "ignore")

    # ── 加密（如需主动回复时用） ──
    def encrypt(self, plaintext: str) -> str:
        msg = bytes(plaintext.encode("utf-8"))
        rand = __import__("os").urandom(16)
        packed = rand + struct.pack(">I", len(msg)) + msg + self.corp_id.encode("utf-8")
        # PKCS7 填充
        pad_len = 32 - (len(packed) % 32)
        packed += bytes([pad_len]) * pad_len
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv).encrypt(packed)
        return base64.b64encode(cipher).decode("utf-8")

    # ── 封装：解密回调 XML ──
    def decrypt_message(self, xml_text: str, msg_signature: str, timestamp: str,
                        nonce: str) -> dict:
        """校验签名并解密回调 XML → 明文消息 dict（含所有节点）。"""
        outer = _parse_xml(xml_text)
        encrypt = outer.get("Encrypt", "")
        if not encrypt:
            raise WXBizMsgCryptError("回调 XML 缺少 Encrypt 节点")
        if not self.verify(msg_signature, timestamp, nonce, encrypt):
            raise WXBizMsgCryptError("签名校验失败")
        return _parse_xml(self.decrypt(encrypt))
