"""AI 配置自检：验证「文本 / 文件识别 / 图像识别」三条链路是否可用。

用法：
    python verify_ai.py

    # 临时覆盖配置（不修改 configs/app.env）
    AI_API_KEY=sk-xxx AI_BASE_URL=https://maas.qianwenaiapi.com/compatible-mode/v1 \
    AI_MODEL=deepseek-v4.1-flash-1017 python verify_ai.py

说明：
- 配置来源为 configs/app.env，环境变量优先级更高；
- 图像测试会动态生成一张带文字的 PNG，能真实检验模型的视觉能力；
- 任一链路失败会打印服务端返回的错误摘要（见 [AI] / [AI-vision] 日志）。
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import get_app_config  # noqa: E402
from core import analyzer  # noqa: E402

PASS = FAIL = 0


def result(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✅ {name}: {detail}")
    else:
        FAIL += 1
        print(f"  ❌ {name}: {detail}")


def make_test_image() -> Path:
    """生成一张带英文文字的测试图（避免服务器缺中文字体）"""
    p = Path(tempfile.mkdtemp(prefix="ai_check_")) / "notice.png"
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (420, 140), "white")
        draw = ImageDraw.Draw(img)
        draw.rectangle([8, 8, 411, 131], outline="black", width=3)
        draw.text((28, 35), "EXAM NOTICE", fill="black")
        draw.text((28, 80), "Math test tomorrow 9:00", fill="black")
        img.save(p)
    except Exception:
        # Pillow 不可用时退化为 1x1 PNG（仅验证接口连通性）
        import base64

        p.write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        ))
    return p


async def main() -> int:
    cfg = dict(get_app_config())
    # 环境变量覆盖（便于临时验证其他平台/模型）
    for k in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL", "AI_MODEL_VISION", "AI_ENABLE_THINKING"):
        if os.environ.get(k):
            cfg[k] = os.environ[k]

    print("══ 当前配置 ══")
    print(f"  base_url : {cfg.get('AI_BASE_URL')}")
    print(f"  model    : {cfg.get('AI_MODEL')}")
    print(f"  vision   : {cfg.get('AI_MODEL_VISION')}")
    key = cfg.get("AI_API_KEY", "")
    print(f"  api_key  : {'已配置（' + key[:6] + '…' + key[-4:] + '）' if key else '❌ 未配置'}")
    print(f"  thinking : {cfg.get('AI_ENABLE_THINKING')}")

    if not key:
        print("\n❌ 未配置 AI_API_KEY，无法测试")
        return 2

    print("\n══ 1. 文本调用（chat_completion）══")
    text = await analyzer.chat_completion(
        cfg, [{"role": "user", "content": "只回复两个字母：OK"}], max_tokens=20)
    result("文本生成", bool(text), repr(text[:60]))

    print("\n══ 2. 文件识别（文本模型 + 文件名/上下文）══")
    info = await analyzer.analyze_file(cfg, "期中考试安排.docx", "班主任说明天考试")
    result("文件识别", isinstance(info, dict) and "important" in info, str(info)[:120])

    print("\n══ 3. 图像识别（视觉模型）══")
    img = make_test_image()
    print(f"  测试图: {img.name} ({img.stat().st_size} bytes)")
    vinfo = await analyzer.analyze_image(cfg, str(img), "群里发的考试通知")
    result("图像识别", isinstance(vinfo, dict) and "desc" in vinfo, str(vinfo)[:160])

    print(f"\n══ 结果: {PASS} 通过 / {FAIL} 失败 ══")
    if FAIL:
        print("\n排查提示：")
        print("  - 400/422：模型名不存在、参数不兼容（enable_thinking 已自动降级）")
        print("  - 401/403：Key 无效或无该模型权限")
        print("  - 图像失败但文本正常：该模型可能不支持视觉，请单独配置 AI_MODEL_VISION")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
