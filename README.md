# 🐱 聊天智能分析助手

自动抓取 **QQ / 钉钉** 群聊消息，用 **deepseek-v4-flash-0731**（阿里云百炼）分析总结，每天定时生成书面报告（docx + html），重要信息即时提醒并给出执行建议。带 Web 管理界面，可部署为公网网站。

## ✨ 功能

- **多平台抓取**：QQ（官方开放平台机器人）+ 钉钉（官方企业内部应用），各平台独立进程、互不干扰；
- **AI 分析**：deepseek-v4-flash-0731 生成日报总结、判断重要信息、输出执行建议（动作/责任人/优先级），支持图片多模态；
- **每日报告**：定时生成 `docx + html` 报告，网页在线预览/下载；
- **重要提醒**：关键词 + AI 双重判定，站内提醒 + 可选 Server酱 推送；
- **实时推送（SSE）**：新消息/新提醒/新报告/新文件毫秒级推送到网页，无需手动刷新（断线自动重连，5s 轮询兜底）；
- **文件库**：群里的**图片/文件自动下载保存**（`data/users/{username}/media/`，按账号隔离），AI 自动识别内容、判断是否为重要资料并**标记 ★ 重要**、打分类标签；「文件库」页支持缩略图预览、下载、按平台/分类/重要筛选、手动标记；重要文件自动生成提醒（AI 视觉模型 `qwen-vl-plus`，图片识别）；
- **Web 界面**：**开放注册 + 登录**（多用户，账号密码 JWT 认证）；消息/报告/提醒/文件页支持 **QQ/钉钉 一键切换**；
- **多租户（每账号独立空间）**：每个账号（含 admin）**绑定自己的 QQ/钉钉账号**（AppID/Secret 存用户库）、**设置自己的关键词库**、数据（消息/提醒/报告/文件/媒体）**按账号完全隔离**（`data/users/{username}/`）；AI 判定/识别**全局共用**管理员提供的 API；**worker 动态扩展**——新用户绑定机器人后 15 秒内自动接入独立连接，无需重启；
- **安全加固**：登录限流/注册开关/JWT 随机化/密码 PBKDF2+盐/改密令牌失效/媒体与文件访问严格限定用户自己目录（越权 400）/SSE 单库异常隔离；
- **公网部署**：Nginx + HTTPS + systemd 守护，详见 `deploy/DEPLOY.md`。

## 🏗 架构

### 进程拓扑

```
浏览器 ─HTTPS→ Nginx(:443) ─反代→ FastAPI Web(:8001, 仅127.0.0.1)
                                      ├─ worker-qq       (为每个启用绑定的用户创建独立连接实例)
                                      ├─ worker-dingtalk (同上)
                                      └─ 命令文件通道 data/commands/{platform}__{user}.json
多租户数据: data/users/{username}/  → qq.db / dingtalk.db / reports/ / media/
```

### 分层与依赖方向

```
config.py（配置/路径）  ◀── 所有层
core/                   业务层（不依赖 web）
  ├─ models             数据模型 DTO
  ├─ accounts/          账户/租户持久化（users 用户、bindings 绑定、keywords 用户词库）
  ├─ keywords           全局默认关键词库（configs/important_keywords.json）
  ├─ storage/           消息存储门面 = base 连接 + 各表仓储 Mixin
  ├─ adapter            平台适配器抽象（线程生命周期 + 消息队列 + 工厂）
  ├─ pipeline           流水线：入库去重 → 关键词 → AI 确认 → 提醒/推送
  ├─ analyzer / reporter / media / commands / console
platforms/              QQ(WebSocket) / 钉钉(轮询) 适配器实现
web/                    表现层（依赖 core，单向）
  ├─ auth               仅 JWT/Cookie 认证；数据访问代理到 core.accounts
  ├─ security           审计日志 / 登录限流 / 注册频控 / CSRF
  ├─ deps               多租户 Storage、运行状态、鉴权/分页/脱敏、报告路径解析
  ├─ routers/           按业务域拆分的路由（认证/账户/概览/消息/提醒/报告/平台/文件/设置/实时流）
  └─ server             应用装配：静态资源 + 中间件 + 路由注册 + SSE 轮询 lifespan
```

## 🚀 本地快速开始

```bash
# 1. 创建虚拟环境（Windows: Python 3.11.9）
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # Windows
# .venv/bin/pip install -r requirements.txt          # Linux/macOS

# 2. 配置
cd configs
cp app.env.example app.env        # 改 ADMIN_PASSWORD / JWT_SECRET / AI_API_KEY
cp qq.env.example qq.env          # 填 QQ_APP_ID / QQ_APP_SECRET / QQ_GROUP_OPENIDS
cp dingtalk.env.example dingtalk.env  # 填 DINGTALK_APP_KEY / APP_SECRET / DINGTALK_CHAT_IDS
cd ..

# 3. 启动
python main.py all     # 启动全部（2 worker + web）
# 或分别启动: python main.py qq | python main.py dingtalk | python main.py web

# 4. 访问
# 浏览器打开 http://127.0.0.1:8001 ，用 configs/app.env 里的账号登录
```

> 本地没配置平台账号时，可运行 `python test_offline.py` 用模拟数据验证全链路（44 项检查）。

## 🔌 平台接入指南

### QQ（官方开放平台，推荐）

1. 打开 [QQ 开放平台](https://q.qq.com)，用 QQ 扫码登录 → 创建机器人（个人可创建，每个 QQ 号最多 5 个）；
2. 记录 **AppID** 与 **AppSecret** → 填入 `configs/qq.env`；
3. 在机器人配置中开启 **「接收所有消息」（全量模式）**，机器人加入目标群；
4. 从机器人收到的 `GROUP_MESSAGE_CREATE` 事件日志中获取群 `group_openid`（或按官方文档查询），填入 `QQ_GROUP_OPENIDS`（逗号分隔，留空 = 接收所有群）。
   - 环境：沙箱 `QQ_ENV=sandbox`，正式 `QQ_ENV=prod`；
   - 无需公网 IP/回调（机器人主动连网关 WebSocket）。

### 钉钉（官方企业内部应用）

1. 打开 [钉钉开放平台](https://open.dingtalk.com) → 应用开发 → **企业内部开发** → 创建应用；
2. 记录 **AppKey / AppSecret** → 填入 `configs/dingtalk.env`；
3. 在「权限管理」申请 **`qyapi_chat_read`**（读取群消息）权限；
4. 让群主/管理员在目标群授权应用，获取群 **chatId** → 填入 `DINGTALK_CHAT_IDS`（逗号分隔）。

## ⚙️ 配置说明

| 文件 | 关键项 | 说明 |
|------|--------|------|
| `configs/app.env` | `ADMIN_USERNAME/PASSWORD` | 首个管理员账号种子（启动时自动创建，上线必改） |
| | `JWT_SECRET` | JWT 签名密钥（随机长串） |
| | `AI_API_KEY` | AI API Key（deepseek-v4-flash-0731 文本 / qwen-vl-plus 视觉 / paraformer-v2 语音，**全局共用**） |
| | `REPORT_HOUR/MINUTE` | 每日报告时间（默认 18:00） |
| | `POLL_INTERVAL` | 钉钉轮询间隔秒数（默认 90） |
| | `SERVERCHAN_KEY` | Server酱 推送密钥（可选） |
| `configs/qq.env` | `QQ_APP_ID/SECRET/ENV/GROUP_OPENIDS/ENABLED` | 全局 QQ 机器人绑定（可选，兼容旧配置）；**每账号可在 Web 设置页绑定自己的凭证** |
| `configs/dingtalk.env` | `DINGTALK_APP_KEY/SECRET/CHAT_IDS/ENABLED` | 全局钉钉绑定（可选）；**每账号可在 Web 设置页绑定自己的凭证** |
| `configs/important_keywords.json` | 全局默认关键词模板 | 每账号另有自己的关键词库（`user_keywords` 表） |

## 🗂 数据与产物

- `data/users/{username}/qq.db` / `dingtalk.db`：**每账号独立**的消息/提醒/报告记录（SQLite，多租户隔离）；
- `data/users/{username}/reports/{platform}/{date}-日报.docx` + `.html`：每账号独立报告；
- `data/users/{username}/media/`：每账号独立的图片/文件/语音保存；
- `data/users.db`：账号 + 每账号的平台绑定（`user_bindings`）+ 关键词库（`user_keywords`）；
- `logs/`：运行日志；`data/commands/`：Web → worker 命令通道（按用户分文件）。

## ☁️ 公网部署

见 [`deploy/DEPLOY.md`](deploy/DEPLOY.md)：Nginx + HTTPS（certbot）+ systemd 三服务（web/qq/dingtalk 互相独立）。

## ⚠️ 风险与合规

- **隐私**：仅监控你有权限访问的群；数据全部存储在自有服务器，不外传；
- **平台规范**：QQ/钉钉均使用官方接口；请遵守各平台服务协议，控制使用频率；
- **安全加固**（内置）：
  - 登录**限流**：同一 IP+账号 5 分钟内失败 5 次锁定 10 分钟（防暴力破解）；
  - **注册开关**：`REGISTER_OPEN`（公网部署建议关闭）+ 可选**邀请码** `REGISTER_INVITE_CODE`；
  - `JWT_SECRET` 为默认值时**启动自动随机化**（旧会话失效）；
  - 审计日志：登录成功/失败/锁定、管理操作均记录到 `logs/web.log`；
  - 密钥接口脱敏回显；报告接口防路径穿越；普通用户写操作一律 403；
- **上线前必做**：修改默认密码、确认 JWT_SECRET 已随机化、HTTPS 部署时设 `COOKIE_SECURE=true`、按需关闭注册；防火墙只开 80/443；
- **AI 成本**：`deepseek-v4-flash-0731` 为付费模型（思考模式消耗较高），重要判定与日报会消耗额度，可按需在 `important_keywords.json` 收窄关键词减少 AI 调用。

## 🧪 离线测试

```bash
python test_offline.py   # 44 项检查：入库去重/关键词/AI确认(打桩)/日报/Web API/多租户隔离/密码
```

## 📦 项目结构

```
main.py            入口（all/qq/dingtalk/web）
launcher.py        多进程启动器
config.py          配置加载与多租户路径
pyproject.toml     项目元数据 + ruff 代码规范配置
core/
  ├─ models.py           数据模型（ChatMessage/ImportantItem/ReportData）
  ├─ console.py          控制台 UTF-8 兼容（Windows GBK 防崩）
  ├─ keywords.py         全局默认关键词库
  ├─ accounts/           账户持久化层：db(连接/哈希) users bindings keywords
  ├─ storage/            存储门面：base + messages/alerts/reports/files/cursors 仓储
  ├─ adapter.py          平台适配器抽象基类 + 工厂
  ├─ pipeline.py         消息处理流水线（去重→关键词→AI→提醒/推送/媒体）
  ├─ analyzer.py         AI 调用（重要性/日报/图片识别/语音转写）
  ├─ reporter.py         日报生成（docx + html）
  ├─ media.py            媒体文件保存
  └─ commands.py         Web→worker 命令文件通道
platforms/         QQ / 钉钉 适配器实现
web/
  ├─ auth.py             JWT/Cookie 认证（数据访问代理到 core.accounts）
  ├─ security.py         审计日志 / 登录限流 / 注册频控 / CSRF 中间件
  ├─ deps.py             路由共享依赖（多租户 Storage/状态/鉴权/脱敏/报告解析）
  ├─ envutil.py          .env 白名单写入
  ├─ sse.py              SSE 广播管理
  ├─ routers/            pages/auth_routes/account/overview/messages/alerts/
  │                      reports/platforms/files/settings/stream
  ├─ server.py           应用装配（create_app）
  └─ static/             前端 SPA（index/login/app.js/style.css）
configs/           各平台配置模板 + 关键词库
deploy/            nginx / systemd / 部署文档
```
