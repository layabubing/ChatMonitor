"""
AI 分析服务：重要性确认 / 日报总结 / 执行建议 / 图片识别 / 语音转写
- OpenAI 兼容接口（默认阿里云百炼 DashScope），支持图片多模态
- 文本模型 deepseek-v4-flash / 视觉模型 qwen-vl / 语音 paraformer-v2
- 具体模型与 base_url 由 configs/app.env 提供，此处仅作兜底默认
"""
from __future__ import annotations

import asyncio
import json
import re

import httpx

from core.models import ChatMessage, ImportantItem, normalize_priority

TIMEOUT = 45.0


def _headers(config: dict) -> dict:
    return {"Authorization": f"Bearer {config.get('AI_API_KEY', '')}", "Content-Type": "application/json"}


def _endpoint(config: dict) -> str:
    base = config.get("AI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
    return f"{base}/chat/completions"


def _content_blocks(text: str, image_urls: list[str] | None = None) -> list:
    """构造多模态 content 数组：有图片时用 image_url，否则纯文本"""
    if not image_urls:
        return [{"type": "text", "text": text}]
    blocks = [{"type": "text", "text": text}]
    for url in image_urls[:3]:  # 最多 3 张，控制成本
        blocks.append({"type": "image_url", "image_url": {"url": url}})
    return blocks


async def chat_completion(config: dict, messages: list[dict], temperature: float = 0.3,
                          max_tokens: int = 2000) -> str:
    """调用大模型（OpenAI 兼容，默认 deepseek-v4-flash-0731 思考模式），返回正文；失败返回空串"""
    if not config.get("AI_API_KEY"):
        return ""
    body = {"model": config.get("AI_MODEL", "deepseek-v4-flash-0731"),
            "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    # 阿里云百炼思考模型：enable_thinking=True 时先输出 reasoning_content，正文在 content
    if config.get("AI_ENABLE_THINKING", "true") == "true":
        body["enable_thinking"] = True
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                _endpoint(config),
                headers=_headers(config),
                json=body,
            )
            if resp.status_code != 200:
                print(f"[AI] API {resp.status_code}: {resp.text[:200]}")
                return ""
            msg = resp.json()["choices"][0]["message"]
            return msg.get("content") or ""   # 思考内容在 reasoning_content，正文取 content
    except Exception as e:  # noqa: BLE001
        print(f"[AI] 调用失败: {e}")
        return ""


def _extract_json(text: str):
    """从模型输出中容错提取 JSON（对象或数组）"""
    if not text:
        return None
    # 去掉 ```json ... ``` 包裹
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except Exception:
        pass
    # 数组优先
    m = re.search(r"\[.*\]", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


# ═══════════════════════════════════════════════
# 重要性确认（双重判定第二层）
# ═══════════════════════════════════════════════

async def confirm_importance(config: dict, msgs: list[ChatMessage]) -> list[ImportantItem]:
    """批量确认消息是否重要，返回确认结果（含建议）"""
    if not msgs:
        return []
    lines = []
    for i, m in enumerate(msgs):
        content = m.content[:120].replace("\n", " ")
        lines.append(f"[{i}] 群:{m.group_name} 人:{m.sender} 消息:{content}")
    prompt = (
        "你是一个校园/社群信息监控助手。下面是几条命中关键词的聊天消息，请逐条判断是否属于「值得关注的重要信息」：\n"
        "1) 安全/紧急/求助类（火灾、受伤、失联、威胁、报警、救助等）→ priority high\n"
        "2) 投诉/维权/财物损失/情绪异常 → priority high 或 medium\n"
        "3) 班级/校园事务通知（考试安排、资料发放、截止提醒、报名、缴费、活动变更、停课等）→ priority medium\n"
        "4) 纠纷/欺凌/冲突 → priority high\n"
        "忽略广告、日常闲聊、与事务无关的内容。\n\n"
        + "\n".join(lines) +
        "\n\n严格输出 JSON 数组，格式: [{\"index\":0,\"important\":true,\"reason\":\"简要原因\","
        "\"suggestion\":\"执行建议（含动作+责任人+优先级）\",\"priority\":\"high|medium|low\"}, ...]，"
        "不重要则 important 为 false。只输出 JSON，不要其他文字。"
    )
    messages = [{"role": "system", "content": "你是严谨的信息审核助手，只输出 JSON。"},
                {"role": "user", "content": prompt}]
    text = await chat_completion(config, messages, temperature=0.1, max_tokens=1500)
    data = _extract_json(text)
    if not isinstance(data, list):
        # 单个对象兜底
        if isinstance(data, dict):
            data = [data]
        else:
            print("[AI] 重要性判定返回无法解析")
            return []
    results: list[ImportantItem] = []
    for item in data:
        if not isinstance(item, dict) or not item.get("important"):
            continue
        idx = item.get("index")
        if idx is None or not (0 <= idx < len(msgs)):
            continue
        m = msgs[idx]
        results.append(ImportantItem(
            platform=m.platform, msg_id=m.msg_id, content=m.content[:500],
            reason=str(item.get("reason", ""))[:300],
            suggestion=str(item.get("suggestion", ""))[:500],
            priority=normalize_priority(item.get("priority", "medium")),
            sender=m.sender, group_name=m.group_name, ts=m.ts,
        ))
    return results


# ═══════════════════════════════════════════════
# 媒体文件识别（AI 识别重要文件）
# ═══════════════════════════════════════════════

async def analyze_image(config: dict, image_path: str, msg_text: str = "") -> dict | None:
    """用视觉模型识别图片内容，返回 {important, desc, category}；失败返回 None"""
    import base64
    from pathlib import Path
    p = Path(image_path)
    if not p.exists():
        return None
    try:
        b64 = base64.b64encode(p.read_bytes()).decode()
    except Exception:
        return None
    data_url = f"data:image/jpeg;base64,{b64}"
    prompt = (
        "识别这张群聊中的图片。判断它是否属于「值得关注的重要资料」（如：作业/试卷/考试通知/"
        "证件/病历/缴费单/报名表/失物照片/事故现场等），并给出一句话内容描述和分类。\n"
        f"消息上下文（可能为空）: {msg_text[:100]}\n"
        "严格输出 JSON: {\"important\":true或false,\"desc\":\"内容描述\",\"category\":\"图片分类(如 作业资料/通知/证件/生活照/其他)\"}"
    )
    messages = [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]}]
    model = config.get("AI_MODEL_VISION", "qwen-vl-plus")
    # 视觉模型专用调用（不走 chat_completion 的 enable_thinking）
    body = {"model": model, "messages": messages, "max_tokens": 500}
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(_endpoint(config), headers=_headers(config), json=body)
            if resp.status_code != 200:
                print(f"[AI-vision] {resp.status_code}: {resp.text[:150]}")
                return None
            text = resp.json()["choices"][0]["message"].get("content") or ""
    except Exception as e:  # noqa: BLE001
        print(f"[AI-vision] 调用失败: {e}")
        return None
    data = _extract_json(text)
    if not isinstance(data, dict):
        return None
    return {
        "important": bool(data.get("important")),
        "desc": str(data.get("desc", ""))[:200],
        "category": str(data.get("category", "其他"))[:30],
    }


async def analyze_file(config: dict, orig_name: str, msg_text: str = "") -> dict | None:
    """文本模型识别文件（非图片）：基于文件名与消息上下文判断重要性"""
    if not config.get("AI_API_KEY"):
        return None
    prompt = (
        "这是一个群聊中发送的文件。文件名: {name}。消息上下文: {ctx}\n"
        "判断它是否属于重要资料（作业/试卷/通知/表格/报名/缴费/证件/公告等），并给出分类。\n"
        "严格输出 JSON: {{\"important\":true或false,\"desc\":\"一句话说明\",\"category\":\"文档/表格/压缩包/其他\"}}"
    ).format(name=orig_name[:100], ctx=(msg_text or "")[:100])
    text = await chat_completion(config, [{"role": "user", "content": prompt}],
                                 temperature=0.1, max_tokens=400)
    data = _extract_json(text)
    if not isinstance(data, dict):
        return None
    return {
        "important": bool(data.get("important")),
        "desc": str(data.get("desc", ""))[:200],
        "category": str(data.get("category", "其他"))[:30],
    }


# ═══════════════════════════════════════════════
# 语音转文字（阿里云百炼 paraformer-v2 异步转写）
# ═══════════════════════════════════════════════

async def transcribe_audio(config: dict, audio_path: str) -> str:
    """语音转文字：上传 → paraformer-v2 异步转写 → 轮询结果；失败返回空串"""
    key = config.get("AI_API_KEY", "")
    if not key:
        return ""
    base = "https://dashscope.aliyuncs.com/api/v1"
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            # 1. 上传音频 → 返回 file_id + 服务器侧 file_path
            from pathlib import Path
            with open(audio_path, "rb") as f:
                r = await c.post(f"{base}/files",
                                 headers={"Authorization": f"Bearer {key}"},
                                 files={"file": (Path(audio_path).name, f, "application/octet-stream")})
            if r.status_code != 200:
                print(f"[ASR] 上传失败 {r.status_code}: {r.text[:200]}")
                return ""
            uploaded = (r.json().get("data") or {}).get("uploaded_files") or []
            if not uploaded:
                return ""
            fid = uploaded[0].get("file_id", "")
            file_path = uploaded[0].get("file_path", "")   # DashScope 服务器侧路径
            if not fid:
                return ""
            # 2. 提交 paraformer-v2 异步转写
            #    file_urls 必须用「公网 URL」或「file:// + 服务器侧本地路径」，
            #    不能用 API 内网地址（服务端无法回访）。
            if file_path.startswith("/"):
                file_url = f"file://{file_path}"
            elif file_path and ":" in file_path:      # Windows 盘符 C:\...
                file_url = f"file://{file_path}"
            else:
                file_url = f"{base}/files/{fid}"      # 兜底（仅当无 file_path）
            r2 = await c.post(f"{base}/services/audio/asr/transcription",
                              headers={"Authorization": f"Bearer {key}", "X-DashScope-Async": "enable"},
                              json={"model": "paraformer-v2",
                                    "input": {"file_urls": [file_url]}})
            if r2.status_code != 200:
                print(f"[ASR] 转写提交失败 {r2.status_code}: {r2.text[:200]}")
                return ""
            task_id = (r2.json().get("output") or {}).get("task_id", "")
            if not task_id:
                return ""
            # 3. 轮询任务结果（最多 60 秒）
            status = ""
            r3 = None
            for _ in range(60):
                await asyncio.sleep(1)
                r3 = await c.get(f"{base}/tasks/{task_id}",
                                 headers={"Authorization": f"Bearer {key}"})
                if r3.status_code != 200:
                    continue
                status = (r3.json().get("output") or {}).get("task_status", "")
                if status in ("SUCCEEDED", "FAILED"):
                    break
            if status != "SUCCEEDED" or r3 is None:
                return ""
            out = r3.json().get("output") or {}
            # 4. 提取文本：results[] 或 transcription_url 结果文件
            text = " ".join(s.get("transcription", "") for s in (out.get("results") or [])).strip()
            if not text and out.get("transcription_url"):
                try:
                    r4 = await c.get(out["transcription_url"])
                    if r4.status_code == 200:
                        try:
                            text = " ".join(s.get("text", "") for s in (r4.json().get("transcripts") or [])).strip()
                        except Exception:
                            text = r4.text.strip()
                except Exception:
                    pass
            return text[:500]
    except Exception as e:  # noqa: BLE001
        print(f"[ASR] 语音转写失败: {e}")
        return ""


# ═══════════════════════════════════════════════
# 日报总结
# ═══════════════════════════════════════════════

async def generate_summary(config: dict, platform: str, msgs: list[ChatMessage],
                           important_items: list[ImportantItem]) -> str:
    """生成当日结构化总结（markdown 文本）"""
    if not msgs:
        return "今日无消息记录。"
    sample = msgs[:60]
    lines = []
    for m in sample:
        lines.append(f"- [{m.group_name}/{m.sender}] {m.content[:100]}")
    imp_lines = "\n".join(
        f"- (优先级:{it.priority}) {it.content[:80]} → 建议:{it.suggestion[:80]}" for it in important_items
    ) or "无"
    prompt = (
        f"请为{platform.upper()}平台今日聊天内容生成一份简明总结报告，包含："
        "1)整体概况(消息量/活跃程度)；2)讨论热点主题(2-4个)；3)情绪倾向；"
        "4)值得关注的事项；5)执行建议清单(每条含动作/责任人/优先级)。\n\n"
        f"今日重要事项:\n{imp_lines}\n\n消息样本:\n" + "\n".join(lines)
    )
    messages = [{"role": "user", "content": prompt}]
    return await chat_completion(config, messages, temperature=0.4, max_tokens=2000)
