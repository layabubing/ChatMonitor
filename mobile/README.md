# ChatMonitor 安卓客户端（Flutter）

ChatMonitor 群聊监控系统的手机端，通过服务器 Web 后端 API + SSE 工作，功能与网页版一致：

- 登录 / 注册（支持邀请码）
- 总览：QQ / 钉钉 / 飞书 / 企业微信各平台统计、运行状态、生成报告 / 暂停 / 恢复 / 重载关键词
  （平台列表由后端 `/api/platforms/meta` 动态下发，后续新增平台 App 免改版）
- 消息：平台切换、群筛选、搜索、分页加载、SSE 增量刷新
- 提醒：优先级色标、未读角标、标记已读 / 全部已读
- 报告：日报列表、HTML 在线预览、docx 下载
- 文件库：分类 / 重要筛选、图片预览、文件下载、标星
- 设置：关键词库编辑、平台绑定配置 + 凭证测试、改昵称、改密码、保活设置
- 后台通知：前台服务保活维持 SSE，收到重要提醒弹系统通知；workmanager 每 15 分钟兜底轮询

## 依赖环境

- Flutter SDK ≥ 3.47（Dart ≥ 3.13）
- Android SDK（platform 36、build-tools、platform-tools）

## 构建

```bash
cd mobile
flutter pub get
flutter analyze                 # 应无 error
flutter build apk --release     # 产物在 build/app/outputs/flutter-apk/app-release.apk
```

国内网络如 `maven.google.com` 不可达，本工程已在 `android/settings.gradle.kts` 与
`android/build.gradle.kts` 配置阿里云镜像，无需额外处理。

## 使用

1. 服务器需部署本项目 Web 后端（`python main.py web` 或 systemd 三件套），并可经
   HTTPS（Nginx）或局域网 HTTP 访问。
2. App 首次启动填写服务器地址（如 `https://your-domain` 或 `http://192.168.x.x:8001`），
   用网页版同一账号登录。
3. 登录后自动启动后台监控服务（常驻通知栏一条"ChatMonitor 运行中"）。
4. 在「设置 → 后台通知（保活）」中按引导关闭电池优化、允许自启动，以保证国产 ROM
   上后台通知的稳定性。

## 服务端配合改动（已在主仓库完成）

- `web/auth.py`：`check_login` 支持 `Authorization: Bearer <jwt>` 回退（网页端 Cookie 不变）
- `web/routers/stream.py`：SSE 的 `message`/`alert` 事件附带群名/发送者/优先级/内容摘要
- `web/routers/messages.py` + `core/storage/messages.py`：`/api/messages` 新增 `since_ts`
  增量查询参数
- `web/routers/platforms.py`：新增 `GET /api/platforms/meta`（平台显示名/绑定键/密钥键，
  由 `PLATFORM_META` 注册表驱动，App 据此动态渲染四平台）

以上均为向后兼容的增量改动，网页端行为不受影响。

## 目录结构

```
lib/
├── main.dart              # 入口、主题、登录门控
├── api/                   # client.dart（全部端点）、models.dart、sse.dart（SSE 客户端）
├── state/app_state.dart   # 全局状态（登录态/总览/SSE 分发，ChangeNotifier）
├── service/keepalive.dart # 前台服务保活、本地通知、workmanager 兜底轮询
├── pages/                 # 登录 + 六个业务页 + 主页框架
└── widgets/common.dart    # 公共组件（徽标/空态/加载/格式化）
```
