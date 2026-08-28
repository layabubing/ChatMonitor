"""
离线端到端验证（不依赖真实平台账号/AI key）
验证: 消息入库去重 → 关键词过滤 → AI 确认(打桩) → 提醒入库 → 日报生成 → Web API 认证
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from core import analyzer  # noqa: E402
from core.models import ChatMessage, ImportantItem  # noqa: E402
from core.pipeline import Pipeline  # noqa: E402
from core.reporter import generate_report  # noqa: E402
from core.storage import Storage  # noqa: E402

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


def main():
    print("══ 1. 存储 + 流水线 ══")
    tmp = Path(tempfile.mkdtemp(prefix="chatmon_test_"))
    # 隔离：web 读 tmp 库、密码修改写 tmp 配置、关键词写 tmp 文件（不污染真实目录）
    import config as cfgmod
    cfgmod.LOGS_DIR = tmp / "logs"   # 审计日志写入临时目录（security.log 动态读 config.LOGS_DIR）
    cfgmod.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    cfgmod.platform_db_path = lambda p: tmp / f"{p}.db"   # 全局库路径隔离（deps.storage 动态读）
    import web.server  # noqa: F401  触发 FastAPI 应用与路由装配
    cfgmod.COMMANDS_DIR = tmp / "commands"
    cfgmod.COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
    from core import commands as _cmds_mod
    _cmds_mod.COMMANDS_DIR = tmp / "commands"   # 命令通道隔离（读真实目录会锁）
    cfgmod.CONFIGS_DIR = tmp / "configs"
    cfgmod.CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    # 多租户：admin 用户数据目录指向临时目录（与 web _storage("qq", "admin") 一致）
    import config as cfg_tenant
    _orig_user_data_dir = cfg_tenant.user_data_dir
    cfg_tenant.user_data_dir = lambda username: tmp / f"user_{username}"
    cfg_tenant.ensure_user_dirs = lambda username: (tmp / f"user_{username}").mkdir(parents=True, exist_ok=True)
    import core.keywords as kw
    kw._KEYWORDS_FILE = tmp / "important_keywords.json"
    # 报告输出隔离到临时目录（避免写真实 reports/ 与预览冲突）
    import core.reporter as _rep_mod
    _rep_mod.platform_report_dir = lambda platform: tmp / "reports" / platform
    # 填充临时关键词库（含测试用词），隔离真实目录
    kw._KEYWORDS_FILE.write_text(json.dumps(
        {"安全": ["着火", "火"], "紧急": ["急", "救命"], "财物": ["丢"]}, ensure_ascii=False), encoding="utf-8")
    kw.load_keywords()

    admin_db = tmp / "user_admin" / "qq.db"
    admin_db.parent.mkdir(parents=True, exist_ok=True)
    storage = Storage(admin_db)   # 与 web _storage("qq", "admin") 同一文件
    config = {"AI_API_KEY": ""}

    # 用固定日期"2099-01-01"的时间戳（毫秒），与日报日期保持一致（避免与真实今日报告/提醒冲突）
    import datetime
    base_ts = int(datetime.datetime(2099, 1, 1).timestamp() * 1000)
    msgs = [
        ChatMessage(msg_id="t1", platform="qq", group_id="g1", group_name="高一群", sender="张三",
                    content="大家好，今天作业好多啊", ts=base_ts + 1),
        ChatMessage(msg_id="t2", platform="qq", group_id="g1", group_name="高一群", sender="李四",
                    content="教学楼3层着火了！快来帮忙！", ts=base_ts + 2),
        ChatMessage(msg_id="t3", platform="qq", group_id="g1", group_name="高一群", sender="王五",
                    content="谁捡到我的手机了，急！", ts=base_ts + 3),
        ChatMessage(msg_id="t4", platform="qq", group_id="g1", group_name="高一群", sender="赵六",
                    content="食堂今天有红烧肉，真香", ts=base_ts + 4),
    ]

    # AI 确认打桩：把"着火"那条判为重要
    async def fake_confirm(cfg, cands):
        return [ImportantItem(platform="qq", msg_id=cands[0].msg_id, content=cands[0].content,
                              reason="疑似火灾，需立即核实", suggestion="联系宿管/保卫处，确认现场情况",
                              priority="high")]
    analyzer.confirm_importance = fake_confirm

    pipeline = Pipeline(storage, config, "qq")
    n = pipeline.process_batch(msgs)
    check("首次入库 4 条", n == 4, f"got {n}")
    n2 = pipeline.process_batch(msgs)
    check("重复消息去重 0 条", n2 == 0, f"got {n2}")

    alerts = storage.query_alerts(platform="qq")["items"]
    check("关键词命中+AI确认生成 1 条提醒", len(alerts) == 1, f"got {len(alerts)}")
    if alerts:
        check("提醒含执行建议", "保卫处" in alerts[0]["suggestion"], alerts[0]["suggestion"])
        check("提醒优先级 high", alerts[0]["priority"] == "high", alerts[0]["priority"])

    res = storage.query_messages("qq", q="着火", page=1)
    check("消息搜索「着火」命中 1 条", res["total"] == 1, f"got {res['total']}")

    print("\n══ 2. 日报生成 ══")
    # 用固定测试日期，避免与真实「今日」报告文件冲突（可能被预览占用）
    rep = generate_report(storage, config, "qq", "2099-01-01")
    check("报告对象生成", rep is not None)
    check("docx 文件存在", rep and Path(rep.docx_path).exists())
    check("html 文件存在", rep and Path(rep.html_path).exists())
    if rep:
        html = Path(rep.html_path).read_text(encoding="utf-8")
        check("html 包含重要事项表格", "重要事项" in html and "着火" in html)

    reports = storage.query_reports("qq")
    check("报告已入库", len(reports) == 1)

    print("\n══ 3. Web API 认证与路由 ══")
    from fastapi.testclient import TestClient
    from web.server import app
    from web import auth

    # 确保 admin 种子在临时用户库中
    auth.set_store_path(tmp / "users.db")
    auth.ensure_admin()

    client = TestClient(app)
    r = client.get("/api/me")
    check("未登录 /api/me → 401", r.status_code == 401, f"got {r.status_code}")

    r = client.post("/api/login", json={"username": "admin", "password": "wrong"})
    check("错误密码 → 401", r.status_code == 401, f"got {r.status_code}")

    r = client.post("/api/login", json={"username": "admin", "password": "change-me-please"})
    check("admin 正确密码 → 200", r.status_code == 200, f"got {r.status_code}")
    token_ok = r.status_code == 200

    if token_ok:
        r = client.get("/api/me")
        check("admin 角色为 admin", r.status_code == 200 and r.json()["role"] == "admin", f"got {r.json()}")
        r = client.get("/api/overview")
        check("登录后可看总览", r.status_code == 200 and "qq" in r.json(), f"got {r.status_code}")
        r = client.get("/api/messages?platform=qq&page=1")
        check("登录后可查消息", r.status_code == 200 and r.json()["total"] == 4)
        r = client.get("/api/alerts")
        check("登录后可查提醒", r.status_code == 200 and r.json()["total"] == 1)
        r = client.get("/api/reports")
        check("登录后可查报告", r.status_code == 200 and len(r.json()["items"]) == 1)
        r = client.post("/api/platforms/qq/command", json={"cmd": "generate_report"})
        check("admin 可下发生成报告命令", r.status_code == 200)
        from core import commands
        pending = commands.get_pending("qq", "admin")
        check("命令文件已写入(用户级)", pending is not None and pending["cmd"] == "generate_report")
        r = client.get("/api/settings")
        check("登录后可看设置", r.status_code == 200 and "keywords" in r.json())
        r = client.get("/api/reports/qq/2026-08-26/html")
        # 该日期报告未必存在，只验证鉴权通道不 401
        check("报告预览路由可访问(非401)", r.status_code != 401, f"got {r.status_code}")

    # ── 注册与权限 ──
    r = client.post("/api/register", json={"username": "zhangsan", "password": "pass123"})
    check("注册新用户成功", r.status_code == 200, f"got {r.status_code}: {r.text}")
    r = client.post("/api/register", json={"username": "zhangsan", "password": "pass456"})
    check("重复用户名注册被拒", r.status_code == 400, f"got {r.status_code}")
    r = client.post("/api/register", json={"username": "ab", "password": "123"})
    check("弱用户名/密码被拒", r.status_code == 400, f"got {r.status_code}")

    r = client.post("/api/login", json={"username": "zhangsan", "password": "pass123"})
    check("新用户可登录", r.status_code == 200, f"got {r.status_code}")
    r = client.get("/api/me")
    check("新用户角色为 user", r.status_code == 200 and r.json()["role"] == "user", f"got {r.json()}")
    r = client.get("/api/overview")
    check("普通用户可看总览(只读)", r.status_code == 200, f"got {r.status_code}")
    r = client.get("/api/messages?platform=qq&page=1")
    check("普通用户可查消息", r.status_code == 200)
    # 多租户：绑定/关键词/命令均为用户级（普通用户操作自己的空间）；AI 全局共用
    r = client.get("/api/settings")
    check("普通用户 settings 含用户级关键词", r.status_code == 200 and "keywords" in r.json() and "ai" in r.json(), f"got {list(r.json().keys())}")
    r = client.post("/api/me/nickname", json={"nickname": "小张三"})
    check("普通用户可改自己昵称", r.status_code == 200, f"got {r.status_code}")
    r = client.post("/api/settings/keywords", json={"categories": {"我的": ["自定义词"]}})
    check("普通用户可保存自己的关键词（多租户）", r.status_code == 200, f"got {r.status_code}")
    r = client.post("/api/settings/platforms/qq", json={"QQ_APP_ID": "", "enabled": False})
    check("普通用户可保存自己的绑定（多租户）", r.status_code == 200, f"got {r.status_code}")
    r = client.post("/api/platforms/qq/command", json={"cmd": "generate_report"})
    check("普通用户可对自己实例下发命令（多租户）", r.status_code == 200, f"got {r.status_code}")
    # 改密码：需旧密码验证；改他人 → 403
    r = client.post("/api/settings/password", json={"username": "admin", "password": "hack12345"})
    check("普通用户改他人密码 → 403", r.status_code == 403, f"got {r.status_code}")
    r = client.post("/api/settings/password", json={"username": "zhangsan", "old_password": "wrong", "password": "newpass123"})
    check("改自己密码旧密码错误 → 400", r.status_code == 400, f"got {r.status_code}")
    r = client.post("/api/settings/password", json={"username": "zhangsan", "old_password": "pass123", "password": "newpass123"})
    check("改自己密码旧密码正确 → 200", r.status_code == 200, f"got {r.status_code}")

    # ── 登录限流（防暴力破解；独立用户名避免影响 admin） ──
    for _ in range(5):
        client.post("/api/login", json={"username": "nobody", "password": "bad"})
    r = client.post("/api/login", json={"username": "nobody", "password": "bad"})
    check("连续失败5次后触发限流 429", r.status_code == 429, f"got {r.status_code}")

    # 关键词库读写
    from core.pipeline import get_keyword_categories, save_keywords
    cats = get_keyword_categories()
    check("关键词库非空", len(cats) > 0)
    cats["测试"] = ["验证词"]
    save_keywords(cats)
    check("关键词库保存", "验证词" in get_keyword_categories()["测试"])

    # 密码修改（多用户：指定用户名）
    ok = auth.update_password("admin", "newpass123")
    check("密码修改成功", ok)
    check("新密码可登录", auth.do_login("admin", "newpass123") is not None)
    check("旧密码失效", auth.do_login("admin", "change-me-please") is None)

    print(f"\n══ 结果: {PASS} 通过 / {FAIL} 失败 ══")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
