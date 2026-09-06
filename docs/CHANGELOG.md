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

### Security

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

### Added

- 新增 `docs/安全审计报告.md`：全项目安全审计技术报告（高危 4 项、中危 15 项、低危 10 项及修复路线图）

[Unreleased]: https://github.com/layabubing/ChatMonitor/compare/v1.0.0...HEAD
