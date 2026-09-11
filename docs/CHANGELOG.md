# 更新日志

本项目的所有重要变更均记录于此文件。

格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。

变更分类约定：

- `Added`：新增功能
- `Changed`：既有功能变更
- `Deprecated`：即将移除的功能
- `Removed`：已移除功能
- `Fixed`：缺陷修复
- `Security`：安全相关修复（含漏洞编号、影响面与修复方式）

## [Unreleased]

### Fixed

- **修复平台绑定「已配置但无法启用」：界面永久显示「已停止」** —— 状态判定与实例创建口径不一致
  - 问题：`main.py` 的 `_collect_instances`（worker 侧）以「全局配置 + 用户绑定覆盖」取值，用户未填写的键沿用全局值，据此判定「与全局凭证相同 → 复用全局实例，不建用户实例」；而 `web/deps.py` 的 `is_alive`（web 侧）只读用户绑定、无全局兜底，判定「用户独立实例」→ 去查 `data/users/{username}/{platform}.alive`，该心跳文件永不会被创建 → 状态恒为「已停止」（**4 个平台均受影响**，逻辑由 `PLATFORM_META` 统一驱动）
  - 触发条件：服务器 `configs/{platform}.env` 配了全局凭证且 `ENABLED=true`，而用户在绑定界面未重新填写 AppID（只填 Secret 或留空）
  - 修复：`is_alive` 改为与 worker 完全一致的口径（`merged = dict(全局配置); merged.update(用户绑定)` 后再取 app_id），两侧判定对齐
- **修复平台绑定的「停用」开关无效** —— 前后端字段名不匹配
  - 问题：前端 `settings.js` 提交平台前缀键（如 `QQ_ENABLED`），后端 `web/routers/platforms.py` 读取的是 `body.get("enabled", True)`，键名不存在导致恒回退 `True`，`user_bindings.enabled` 恒为 1 —— 界面选「停用」完全不生效（**4 个平台均受影响**）
  - 修复：后端兼容两种键名（优先 `enabled`，缺失时读 `{平台}_ENABLED`）并归一化取值（`1/true/yes/on`），保持向后兼容
- **加固 worker 异常隔离**（`main.py`）：心跳文件写入与 `adapter.start()` 各自包裹异常处理，单点失败不再中断 worker 主循环或影响其它实例启动

## [2.0.0] - 2026-09-11

### Added

- **飞书平台接入**（#794370c）：长连接 WebSocket 模式，无需公网回调
  - `platforms/feishu.py`：文本 / 富文本 / 图片 / 语音 / 文件消息解析；连接后 `ClientRegister` 注册，25s 心跳保活
  - 配置模板 `configs/feishu.env.example`；systemd 单元 `deploy/chat-monitor-feishu.service`
- **企业微信接入**（#794370c）：回调模式
  - `web/wxmsgcrypt.py`：官方 `WXBizMsgCrypt` AES 加解密；`web/routers/workwechat.py`：`/api/workwechat/callback`（URL 验证 + 消息接收 + 失败限流）
  - `core/inbox.py` 跨进程收件箱：web 回调进程写入 → worker 轮询消费，按 CorpID 分目录隔离
  - 配置模板 `configs/workwechat.env.example`；systemd 单元 `deploy/chat-monitor-workwechat.service`
- **`PLATFORM_META` 平台注册表**（`config.py`）：收敛 13 处平台硬编码，新增平台 = 注册表加一行 + 写适配器；`core/adapter.py` 工厂改为查表分发
- **平台扩展回归测试** `test_platforms_ext.py`（32 项）：注册表 / 飞书消息解析 / 企微加解密 / 收件箱多租户隔离 / 回调端到端 / 限流
- **移动端 `mobile/`（Flutter）**（#481e6fb）：全局应用状态管理（`AppState`，含登录态 / 概览数据 / SSE 事件处理）与通用组件（平台徽章、优先级徽章、空态 / 错误态 / 加载更多指示器）
- 新增 `docs/安全审计报告.md`：全项目安全审计技术报告（高危 4 项、中危 15 项、低危 10 项及修复路线图）

### Changed

- `core/adapter.py`：适配器工厂由 if-else 分支改为注册表查表（`create()` 接口与返回值不变）
- `core/inbox.py`：`pop_messages()` 增加 `scope` 参数（默认 `None`，向后兼容）
- `web/routers/stream.py`：SSE 载荷增加 `preview` / `group_name` 等字段（只增不减，前端兼容）
- `web/auth.py`：兼容 `Authorization: Bearer` 头认证（Cookie 认证仍为主路径）
- 前端：新增四平台 tab 与飞书 / 企微绑定表单；`web/static/js/pages/settings.js` 字段渲染改注册表化（`FIELD_MAP`）
- `requirements.txt`：新增 `pycryptodome`

- `test_offline.py`：注册流程测试在隔离配置目录显式写入 `REGISTER_OPEN=true`（配合默认关闭注册的新行为）

- **修复 H3：AI 输出 `priority` 未校验导致的存储型 XSS**（高危，见 `docs/安全审计报告.md`）
  - 问题：`alerts.priority` 直接取 AI 输出入库（可被群内成员通过提示注入控制），总览页 `innerHTML` 拼接未转义，可定向攻击查看"总览"页的管理员
  - 修复：`core/models.py` 新增 `PRIORITIES` 白名单与 `normalize_priority()`（非法值回退 `medium`），`ImportantItem.__post_init__` 强制净化（覆盖全部写入方）；`core/analyzer.py` AI 判定结果显式过白名单；`web/static/js/pages/overview.js` priority 改用 `esc()` 转义；`core/reporter.py` 日报 HTML 的 priority（含 class 属性）改用 `_esc()`，`_esc` 增补引号转义
  - 影响面：存量库中合法值（`high`/`medium`/`low`，大小写/空白容忍）不受影响；历史恶意值在读取渲染侧已被转义兜底

- **修复 H1：注册用户名未校验导致的多租户路径穿越漏洞**（高危，见 `docs/安全审计报告.md`）
  - 问题：`create_user` 仅校验用户名长度（3–32），用户名直接拼接为文件系统路径；攻击者可注册 `../users/victim` 类用户名越权读写其他租户数据，或在任意可写位置创建目录与文件
  - 修复：`config.py` 新增 `USERNAME_RE` 白名单（`[A-Za-z0-9_-]{3,32}`）与 `is_valid_username()`，`core/accounts/users.py` 注册时强制执行白名单校验；`config.user_data_dir()` 增加 `is_safe_path_username()` 纵深防御（拒绝 `.`/`..`/路径分隔符/NUL，非法用户名直接抛出 `ValueError` 失败关闭），兼容存量中文用户名
  - 影响面：存量合法用户（含中文用户名）不受影响；含路径分隔符的存量恶意用户名将无法再访问任何数据接口
- **修复 H2：`/api/media/raw` 路径穿越导致任意登录用户可拖库**（高危，见 `docs/安全审计报告.md`）
  - 问题：`web/routers/files.py` 仅做字符串前缀检查，resolve 后只校验"在 `data/` 内"，`users/<自己>/media/../../../users.db` 可下载全站凭据库
  - 修复：新增 `_resolve_user_media()` 统一校验，resolve 后必须以"当前用户 media 目录"为边界（`Path.is_relative_to`），越界一律 400；`/api/files/{platform}/{fid}/raw` 复用同一校验
- 验证：`test_offline.py` 44 项、`test_platforms_ext.py` 32 项全部通过；针对 H1/H2 攻击载荷（`../`、`..\\`、`%2e` 编码变体）的回归断言全部通过

### Fixed

- **飞书 / 企业微信适配器代码审查修复**（平台扩展代码审查编号，独立于 `docs/安全审计报告.md` 的 H/M/L 编号体系）
  - S1：企微多租户收件箱竞态 —— `core/inbox.py` 由共享目录改为按 CorpID 分目录，worker 只消费自身 CorpID 目录，消除多实例竞争同一目录导致的丢消息
  - M1：平台凭证 Token 日志脱敏，避免 Secret / Token 出现在日志输出
  - M2：飞书断线检测 —— 心跳 send 失败即主动 close 触发重连，去掉 70s 固定空超时导致的误判
  - L1：企微媒体消息只收 `MediaId`，弃用 `PicUrl` / `ThumbMediaId`，避免重复下载与错误链路
  - L2：回调签名校验改用 `hmac.compare_digest`，防时序攻击
  - L3：企微回调失败限流 —— 60s 窗口阈值 30，成功后复位

### Security

- **修复 H4：移动端默认明文 HTTP 导致凭证可明文传输**（高危，见 `docs/安全审计报告.md`）
  - 问题：裸地址自动补 `http://` 且登录页提示语引导使用 HTTP，密码/JWT/平台密钥可被同网段嗅探
  - 修复：`mobile/lib/state/app_state.dart` 登录/注册的默认协议改为 `https://`；`mobile/lib/pages/login_page.dart` 输入 `http://` 地址时显示醒目明文风险警告，提示语改为推荐 HTTPS
  - 残余说明：`AndroidManifest.xml` 保留 `usesCleartextTraffic="true"`（已加注释说明），因为 `deploy/DEPLOY.md` 支持"无域名 IP + HTTP"内网部署，移除会使该模式在 Android 9+ 完全不可用；明文路径现仅限用户显式输入 `http://` 且已知情警告。公网发布版本建议删除该属性彻底禁止明文
- **修复 M1：JWT 中的角色取自令牌而非数据库**（中危）
  - 问题：管理员被降级/禁用后，旧 token 在 7 天有效期内仍持原角色
  - 修复：`web/auth.py` `verify_token` 的 `role` 改为以数据库实时值为准，权限变更立即生效
- **修复 M3：注册频控只计成功次数且注册默认开放**（中危）
  - 问题：失败尝试不计数，攻击者可持续批量建号（缓慢磁盘 DoS）；`REGISTER_OPEN` 默认 `true`
  - 修复：`web/routers/auth_routes.py` 改为每次尝试即计数（同 IP 10 分钟 5 次上限）；`config.py` 与 `configs/app.env.example` 的 `REGISTER_OPEN` 默认值改为 `false`（默认安全，内网/受控环境按需开启或配置邀请码）
- **修复 M13：`.gitignore` 漏排除 `feishu.env`/`workwechat.env`**（中危）
  - 修复：改为 `configs/*.env` 通配 + `!configs/*.env.example` 例外，`git check-ignore` 验证四个平台 env 均被忽略、example 模板不受影响

[Unreleased]: https://github.com/layabubing/ChatMonitor/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/layabubing/ChatMonitor/compare/v1.0.0...v2.0.0
