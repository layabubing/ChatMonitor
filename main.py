"""
聊天智能分析助手 — 入口
用法:
  python main.py all         # 启动全部(2 worker + web)
  python main.py qq          # 只启动 QQ worker
  python main.py dingtalk    # 只启动钉钉 worker
  python main.py web         # 只启动 Web UI
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apscheduler.schedulers.background import BackgroundScheduler  # noqa: E402

from config import (DATA_DIR, PLATFORM_META, PLATFORMS, ensure_dirs,  # noqa: E402
                    get_platform_config, platform_db_path)  # noqa: E402
from core import accounts, commands, console, keywords  # noqa: E402

console.setup()   # Windows 控制台 UTF-8，避免 emoji 日志崩溃

from core.adapter import PlatformAdapter  # noqa: E402
from core.pipeline import Pipeline  # noqa: E402
from core.storage import Storage  # noqa: E402
_ALIVE_FILE = lambda p: DATA_DIR / f"{p}.alive"  # noqa: E731


def _collect_instances(platform: str, config: dict) -> list[dict]:
    """收集实例：全局（旧配置兼容）+ 每个启用绑定的用户（动态扫描，供定期重扫）"""
    instances: list[dict] = []
    global_enabled = config.get(f"{platform.upper()}_ENABLED", "false") == "true"
    app_id_key = PLATFORM_META[platform]["app_id_key"]
    global_appid = config.get(app_id_key, "")
    # 全局实例（qq.env/dingtalk.env 仍启用时）
    if global_enabled and global_appid:
        instances.append({"username": "", "config": config})
    # 用户级实例：仅当「全局已启用 且 用户凭证与全局相同」时复用全局实例而跳过；
    # 否则每个启用绑定的用户都独立创建实例（相同 AppID 的不同用户互不去重，
    # 避免误判导致用户被跳过 → 无实例/无心跳 → 界面显示已停止）
    for u in accounts.list_bound_users(platform):
        cfg = dict(config)
        cfg.update(u["config"])
        cfg[f"{platform.upper()}_ENABLED"] = "true"
        u_appid = cfg.get(app_id_key, "")
        if global_enabled and u_appid and u_appid == global_appid:
            print(f"[{platform}] 用户 {u['username']} 的凭证与全局相同，复用全局实例")
            continue
        instances.append({"username": u["username"], "config": cfg})
    return instances


def _make_inst(platform: str, inst: dict) -> None:
    """为单个实例创建 storage/pipeline/adapter"""
    username = inst["username"]
    if username:
        from config import ensure_user_dirs, user_platform_db_path
        ensure_user_dirs(username)
        db_path = user_platform_db_path(username, platform)
    else:
        db_path = platform_db_path(platform)
    storage = Storage(db_path)
    pipeline = Pipeline(storage, inst["config"], platform, username)
    adapter = PlatformAdapter.create(platform, inst["config"], username)
    inst.update(storage=storage, pipeline=pipeline, adapter=adapter, started=False)


def run_worker(platform: str) -> None:
    """运行单个平台 worker 进程（多租户：动态维护每用户独立实例）"""
    config = get_platform_config(platform)
    ensure_dirs()

    instances: list[dict] = _collect_instances(platform, config)
    for inst in instances:
        _make_inst(platform, inst)
    if not instances:
        print(f"[{platform}] 无启用绑定（全局未启用且无用户绑定），退出")
        return
    print(f"[{platform}] worker 启动，实例数: {len(instances)} "
          f"({', '.join(i['username'] or 'global' for i in instances)})")

    # 清空残留命令（全局 + 各用户），避免启动即触发 restart 退出
    commands.consume_commands(platform)
    for inst in instances:
        if inst["username"]:
            commands.consume_commands(platform, inst["username"])
    should_exit = {"flag": False}

    def _sync_instances():
        """定期重扫绑定列表：新增用户实例 / 移除停用实例 / 配置变更重建实例（多租户动态扩展）"""
        fresh = _collect_instances(platform, config)
        fresh_map = {i["username"]: i for i in fresh}
        cur_map = {i["username"]: i for i in instances}
        # 移除已停用/删除的实例
        for inst in list(instances):
            if inst["username"] and inst["username"] not in fresh_map:
                try:
                    inst["adapter"].stop()
                except Exception:  # noqa: BLE001
                    pass
                instances.remove(inst)
                print(f"[{platform}] 已移除实例: {inst['username'] or 'global'}")
        # 配置变更（改绑定凭证/开关）→ 重建实例（无需重启 worker）
        for uname, f in fresh_map.items():
            if not uname:
                continue
            cur = cur_map.get(uname)
            if cur and cur["config"] != f["config"]:
                try:
                    cur["adapter"].stop()
                except Exception:  # noqa: BLE001
                    pass
                instances.remove(cur)
                _make_inst(platform, f)
                instances.append(f)
                print(f"[{platform}] 绑定变更，重建实例: {uname}")
        # 新增用户实例
        for f in fresh:
            if f["username"] and f["username"] not in {i["username"] for i in instances}:
                _make_inst(platform, f)
                instances.append(f)
                print(f"[{platform}] 已新增实例: {f['username']}")
        # 启动所有未启动的 adapter
        for inst in instances:
            if not inst.get("started"):
                inst["adapter"].start()
                inst["started"] = True
                print(f"[{platform}] 实例启动: {inst['username'] or 'global'}")

    _sync_instances()   # 首轮同步（含启动 adapter）

    def _consume_cmds():
        # 全局命令文件 + 每个用户的命令文件
        items = []
        items += [("", c) for c in commands.consume_commands(platform)]
        for inst in instances:
            if inst["username"]:
                for c in commands.consume_commands(platform, inst["username"]):
                    items.append((inst["username"], c))
        for target, c in items:
            cmd = c.get("cmd", "")
            try:
                if cmd == "generate_report":
                    for inst in instances:
                        if target and inst["username"] != target:
                            continue
                        inst["pipeline"].build_daily_report((c.get("payload") or {}).get("date"))
                elif cmd == "pause":
                    for inst in instances:
                        if target and inst["username"] != target:
                            continue
                        inst["pipeline"].pause()
                    print(f"[{platform}] 已暂停抓取")
                elif cmd == "resume":
                    for inst in instances:
                        if target and inst["username"] != target:
                            continue
                        inst["pipeline"].resume()
                    print(f"[{platform}] 已恢复抓取")
                elif cmd == "reload_keywords":
                    for inst in instances:
                        if target and inst["username"] != target:
                            continue
                        keywords.load_keywords()
                        if inst["username"]:
                            inst["pipeline"]._user_words = accounts.flatten(
                                accounts.get_user_keywords(inst["username"]))
                    print(f"[{platform}] 关键词已重载，正在补判定当日消息…")
                    for inst in instances:
                        if target and inst["username"] != target:
                            continue
                        inst["pipeline"].rescan_today()
                elif cmd == "restart":
                    print(f"[{platform}] 收到 restart，退出进程（systemd/launcher 将自动拉起）")
                    should_exit["flag"] = True
            except Exception as e:  # noqa: BLE001
                print(f"[{platform}] 命令执行失败 {cmd}: {e}")

    scheduler = BackgroundScheduler()
    scheduler.add_job(_consume_cmds, "interval",
                      seconds=max(2, int(config.get("COMMAND_INTERVAL", 3))),
                      id=f"cmds_{platform}")
    # 定期重扫绑定（多租户动态实例：新绑定用户自动接入）
    scheduler.add_job(_sync_instances, "interval", seconds=15, id=f"sync_{platform}")
    for inst in instances:
        scheduler.add_job(lambda i=inst: i["pipeline"].build_daily_report(), "cron",
                          hour=int(config.get("REPORT_HOUR", 18)),
                          minute=int(config.get("REPORT_MINUTE", 0)),
                          id=f"daily_{platform}_{inst['username'] or 'global'}")
    scheduler.start()

    last_alive = 0.0

    try:
        while True:
            if should_exit["flag"]:
                break
            for inst in instances:
                for msg in inst["adapter"].iter_messages(timeout=0.5):
                    inst["pipeline"].process_batch([msg])
            # 心跳文件（web 判断运行状态；仅写实际存在的实例对应心跳）
            now = time.time()
            if now - last_alive >= 30:
                has_global = any(not inst["username"] for inst in instances)
                if has_global:
                    _ALIVE_FILE(platform).write_text(str(int(now)))
                for inst in instances:
                    if inst["username"]:
                        from config import user_data_dir
                        (user_data_dir(inst["username"]) / f"{platform}.alive").write_text(str(int(now)))
                last_alive = now
            time.sleep(0.3)
    except KeyboardInterrupt:
        print(f"\n[{platform}] 正在退出…")
    finally:
        for inst in instances:
            inst["adapter"].stop()
        scheduler.shutdown(wait=False)


def run_web() -> None:
    """启动 Web UI（仅监听本机）"""
    import uvicorn
    from config import get_app_config
    from web import auth as web_auth
    web_auth.ensure_secure_secret()   # 默认 JWT_SECRET 自动加固
    web_auth.ensure_admin()           # 确保 admin 种子账号存在
    web_auth.warn_default_password()  # 默认密码警告
    cfg = get_app_config()
    host = cfg.get("WEB_HOST", "127.0.0.1")
    port = int(cfg.get("WEB_PORT", 8001))
    print(f"[web] 仪表盘: http://{host}:{port}  (admin 账号由 app.env 初始化)")
    uvicorn.run("web.server:app", host=host, port=port, log_level="warning")


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    if target == "all":
        import launcher
        launcher.launch_all()
    elif target in PLATFORMS:
        run_worker(target)
    elif target == "web":
        run_web()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
