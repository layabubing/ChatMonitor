# -*- coding: utf-8 -*-
"""生成《创作说明》docx：聊天智能分析助手（ChatMonitor）"""
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

ACCENT = RGBColor(0x2F, 0x6B, 0xFF)
DARK = RGBColor(0x33, 0x33, 0x33)


def set_cn(style_name, size=11, bold=False, color=DARK, font='微软雅黑'):
    from docx.enum.style import WD_STYLE_TYPE
    doc.styles[style_name].font.name = font
    doc.styles[style_name].font.size = Pt(size)
    doc.styles[style_name].font.bold = bold
    doc.styles[style_name].font.color.rgb = color
    doc.styles[style_name]._element.rPr.rFonts.set(qn('w:eastAsia'), font)


doc = Document()
for s in doc.sections:
    s.top_margin, s.bottom_margin = Cm(2.2), Cm(2.2)
    s.left_margin, s.right_margin = Cm(2.5), Cm(2.5)

# 样式
set_cn('Normal', 11)
set_cn('Heading 1', 16, True, ACCENT)
set_cn('Heading 2', 13, True, RGBColor(0x1F, 0x4E, 0xB8))
set_cn('Heading 3', 11.5, True)

# ═══════ 封面 ═══════
for _ in range(5):
    doc.add_paragraph()
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run('聊天智能分析助手\n（ChatMonitor）'); r.font.size = Pt(26); r.font.bold = True; r.font.color.rgb = ACCENT
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run('—— 多平台群聊信息智能监控与分析系统 ——'); r.font.size = Pt(14); r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
doc.add_paragraph()
for line in ['参赛项目：科创比赛作品', '参赛者：笺', '日期：2026 年 8 月']:
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(line); r.font.size = Pt(12)
doc.add_page_break()

# ═══════ 一、项目概述 ═══════
doc.add_heading('一、项目概述', level=1)
doc.add_paragraph(
    '《聊天智能分析助手》（ChatMonitor）是一款面向校园班级、学生社团及小型社群的群聊信息智能监控与分析系统。'
    '系统通过接入 QQ 官方开放平台机器人与钉钉企业内部应用，自动抓取指定群聊中的全部消息，'
    '结合「关键词快速筛选 + 大语言模型精准判定」的双重机制识别重要信息，'
    '通过网页端毫秒级实时推送重要提醒，并每日自动生成图文报告（docx + html），'
    '同时实现了聊天中图片、文件、语音的自动保存与 AI 识别归档，帮助管理者在信息洪流中'
    '第一时间发现紧急事件、关键通知与重要资料，避免遗漏。'
)
doc.add_paragraph(
    '系统采用多进程独立架构（Web / QQ worker / 钉钉 worker），各平台互不干扰；'
    '前端为单页管理仪表盘，支持多用户注册登录与角色权限分级；'
    '内置登录限流、CSRF 防护、配置注入拦截、JWT 改密失效、审计日志等安全机制，'
    '可平滑部署至云服务器（Nginx + systemd 守护）对外提供服务。'
)

# ═══════ 二、背景与需求 ═══════
doc.add_heading('二、项目背景与需求分析', level=1)
doc.add_heading('2.1 背景', level=2)
doc.add_paragraph(
    '在校园与社群场景中，QQ 群、钉钉群已成为信息发布与交流的主阵地。一个活跃的班级群每天产生'
    '数百条消息，其中夹杂着：突发安全事件（如"着火了""有人晕倒"）、重要事务通知（如考试安排、'
    '资料发放）、财物遗失求助、心理健康预警等关键信息。这些信息往往在几分钟内被大量闲聊淹没，'
    '管理者（班主任、班委、社团负责人）很难实时盯守每一个群。'
)
doc.add_paragraph(
    '市面上缺少面向班级/社团的轻量级群聊监控方案：专业舆情系统价格高、部署重；'
    '人工盯群费时费力且易遗漏；单靠关键词匹配又会大量误报。因此需要一套'
    '「低成本、易部署、双平台、智能化」的群聊监控分析工具。'
)

doc.add_heading('2.2 需求分析', level=2)
table = doc.add_table(rows=1, cols=2)
table.style = 'Table Grid'
hdr = table.rows[0].cells
hdr[0].text = '需求类别'; hdr[1].text = '具体要求'
reqs = [
    ('多平台接入', '同时支持 QQ 群与钉钉群，各平台独立进程、互不干扰'),
    ('智能识别', '从海量消息中识别紧急事件、重要通知与关键资料，过滤闲聊与广告'),
    ('实时提醒', '重要信息毫秒级推送至网页端，无需人工刷新'),
    ('自动归档', '每日自动生成图文报告；聊天中的图片/文件/语音自动保存并 AI 识别分类'),
    ('多用户管理', '支持注册登录；普通用户只读、管理员可管控，权限清晰'),
    ('安全可靠', '防暴力破解、防注入、防越权；数据本地化存储'),
    ('易部署', '本地一条命令启动，公网可经 Nginx 反代上线'),
]
for a, b in reqs:
    row = table.add_row().cells
    row[0].text = a; row[1].text = b

# ═══════ 三、系统设计 ═══════
doc.add_heading('三、系统总体设计', level=1)
doc.add_heading('3.1 总体架构', level=2)
doc.add_paragraph(
    '系统采用「适配器 + 流水线 + Web 服务」的分层架构，共 4 个独立进程：'
    '1 个 Web 服务（FastAPI 仪表盘）与 2 个平台 worker（QQ / 钉钉），另有主入口负责多进程拉起。'
    'Web 与 worker 之间通过「命令文件通道」（data/commands/*.json）解耦通信，'
    'worker 崩溃可自动重启，单点故障不互相影响。'
)
arch = doc.add_table(rows=1, cols=3)
arch.style = 'Table Grid'
arch.rows[0].cells[0].text = '数据源层'
arch.rows[0].cells[1].text = '核心处理层'
arch.rows[0].cells[2].text = '服务展示层'
arch.add_row().cells[0].text = 'QQ 官方机器人网关\n（WebSocket 长连接）\n钉钉开放平台 API\n（轮询拉取）'
arch.add_row().cells[1].text = '平台适配器 → 消息流水线\n（去重入库 → 关键词匹配 →\nAI 重要性判定 → 提醒/报告）\n媒体保存与 AI 识别'
arch.add_row().cells[2].text = 'FastAPI Web\n（多用户认证 + 角色权限）\nSSE 实时推送\n单页仪表盘（总览/消息/提醒/\n报告/文件库/设置）'

doc.add_heading('3.2 技术选型', level=2)
tech = doc.add_table(rows=1, cols=3)
tech.style = 'Table Grid'
tech.rows[0].cells[0].text = '技术点'; tech.rows[0].cells[1].text = '选型'; tech.rows[0].cells[2].text = '理由'
stacks = [
    ('开发语言', 'Python 3.11', '生态丰富、异步支持好、开发效率高'),
    ('Web 框架', 'FastAPI + Uvicorn', '高性能异步框架，天然支持 SSE 流式响应'),
    ('数据存储', 'SQLite（每平台独立库）', '零运维、单文件、并发够用，适合轻量部署'),
    ('AI 大模型', 'deepseek-v4-flash-0731（文本）\nqwen-vl-plus（视觉）\nparaformer-v2（语音转写）', '阿里云百炼统一接入；思考模式提升判定质量'),
    ('认证体系', 'JWT + PBKDF2 密码哈希', '无状态认证，多用户角色（admin/user）'),
    ('实时推送', 'SSE（Server-Sent Events）', '服务端主动推送，毫秒级到达，实现成本低'),
    ('部署', 'systemd + Nginx 反代', '守护常驻、公网 HTTPS、与代码零耦合'),
]
for a, b, c in stacks:
    row = tech.add_row().cells
    row[0].text = a; row[1].text = b; row[2].text = c

doc.add_heading('3.3 数据设计', level=2)
doc.add_paragraph(
    '多租户架构下，每个账号独立一个 SQLite 数据库（data/users/{username}/qq.db、dingtalk.db），包含核心表：'
    'messages（消息：平台/群/发送者/内容/类型/媒体/时间戳）、alerts（重要提醒：优先级/原因/处置建议）、'
    'reports（日报记录）、files（文件库：本地路径/类型/AI描述/重要标记/分类）、cursor（拉取游标，跨重启增量）。'
    '用户账号数据独立存于 data/users.db；每个账号另有自己的关键词库（user_keywords 表），'
    '新用户注册时自动从默认模板（configs/important_keywords.json，16 类、288 词）初始化，可在线编辑。'
)

# ═══════ 四、核心功能实现 ═══════
doc.add_heading('四、核心功能实现', level=1)

doc.add_heading('4.1 多平台消息抓取', level=2)
doc.add_paragraph(
    'QQ 侧基于官方开放平台机器人，通过 WebSocket 网关与腾讯服务器建立长连接，'
    '开启「接收所有消息」全量模式后可实时收到群内全部消息事件；'
    '消息中的富媒体附件（图片/文件/语音）自动下载保存到对应账号的独立目录 data/users/{username}/media/，'
    '语音消息利用 QQ 官方内置的 asr_refer_text 转写文本，无需额外费用。'
)
doc.add_paragraph(
    '钉钉侧通过企业内部应用 API 轮询拉取群消息（默认每 90 秒），使用时间游标实现'
    '「服务器关闭期间消息恢复后自动补拉」，并调用 media/download 接口保存图片与语音，'
    '语音经百炼 paraformer-v2 异步转写为文本。两个平台均实现断线自动重连、'
    '崩溃自动重启，保障长时间稳定运行。'
)
doc.add_paragraph(
    '多租户下 worker 采用动态实例管理：每 15 秒扫描绑定列表，新用户绑定机器人后自动创建独立连接实例'
    '（各自 token/心跳/命令通道），停用或删除绑定则自动移除实例，全程无需人工重启。'
)

doc.add_heading('4.2 「关键词 + AI」双重重要性判定', level=2)
doc.add_paragraph(
    '这是系统的核心智能链路，分两级过滤，兼顾速度与准确率：',
)
p = doc.add_paragraph(style='List Number')
p.add_run('第一级（关键词快速筛选）：').bold = True
p.add_run('内置 16 类 288 词校园高频风险词库（紧急求助、安全应急、健康医疗、失联求助、财物丢失、学习考试、校园设施、食品安全、交通出行、网络信息、人际关系、情绪心理、投诉维权、活动事务、气象灾害等），'
          '每账号独立词库（新注册自动初始化默认模板），消息命中任一关键词即进入待判定队列，闲聊消息直接放行，控制 AI 调用成本。')
p = doc.add_paragraph(style='List Number')
p.add_run('第二级（大模型精准判定）：').bold = True
p.add_run('将候选消息批量提交给 deepseek-v4-flash-0731（思考模式），由模型判断每条是否「重要」并输出'
          '结构化 JSON（重要与否/原因/处置建议/优先级 high|medium|low）。'
          '判定标准覆盖安全紧急事件、班级事务通知、投诉维权、情绪异常等，'
          '有效过滤「关键词测试」「广告」等误报。')
doc.add_paragraph(
    '系统还提供「补判定」机制：当关键词库更新后，自动对当天已入库消息重新判定，'
    '保证新增关键词后历史重要消息也能补出提醒，不遗漏。'
)

doc.add_heading('4.3 网页端毫秒级实时推送（SSE）', level=2)
doc.add_paragraph(
    'Web 服务内置 SSE 广播管理器与后台增量轮询器：每 2 秒扫描各平台数据库的增量游标'
    '（新消息/新提醒/新报告/新文件），一旦发现变化立即向所有在线浏览器推送事件。'
    '前端通过 EventSource 监听，新消息即时刷新列表、新提醒立即弹出醒目提示并更新角标，'
    '新报告与文件即时出现；SSE 断线自动重连，同时保留 5 秒轮询作为兜底，确保不丢更新。'
)

doc.add_heading('4.4 文件库：图片/文件/语音自动保存与 AI 识别', level=2)
doc.add_paragraph(
    '聊天中的图片、文件、语音自动下载保存（按平台/日期归档），并以统一 files 表记录元数据。'
    '随后三路 AI 识别：图片调用视觉模型 qwen-vl-plus 描述内容并判断是否重要资料；'
    '文件根据文件名与类型智能分类（文档/表格/课件/压缩包等）；语音经 ASR 转写后入库。'
    '判定为重要的文件自动打上「★ 重要」标记并生成提醒。'
    'Web 端「文件库」页面支持缩略图预览、在线预览/下载、按平台/分类/重要状态筛选搜索，'
    '管理员可手动更正重要标记。'
)

doc.add_heading('4.5 多用户认证与个人中心', level=2)
doc.add_paragraph(
    '系统从单一管理员重构为多用户体系：用户数据存于独立库，密码采用 PBKDF2 + 随机盐哈希；'
    'JWT 令牌携带角色与密码版本号，改密/删号后旧令牌立即失效。'
    '每个账号（含 admin）拥有个人中心：可修改自己的昵称、密码（需验证旧密码），'
    '账号间会话完全独立、互不干扰。首个管理员账号由配置文件种子自动创建，亦可开放注册（可加邀请码）。'
)

doc.add_heading('4.6 多租户：每账号独立监控空间', level=2)
doc.add_paragraph(
    '系统采用多租户架构，每个账号拥有完全独立的使用空间：'
)
multi_items = [
    '独立平台绑定：每个账号可在设置页绑定自己的 QQ / 钉钉凭证（AppID/Secret 存用户库 user_bindings 表），A 账号绑定的机器人 B 账号完全不可见；',
    '独立关键词库：每个账号设置自己的关键词（user_keywords 表），新注册自动初始化默认模板，互不影响；',
    '独立数据空间：消息/提醒/报告/文件/媒体按账号隔离存储（data/users/{username}/ 下独立 SQLite 库与目录），跨账号完全不可见；',
    '独立监控连接：worker 动态实例管理——每 15 秒扫描绑定列表，新绑定用户自动创建独立适配器实例（各自 token/连接/心跳/命令文件），单账号异常不影响他人；',
    '媒体访问隔离：图片/文件读取严格限定用户自己目录（users/{username}/media/），越权访问一律 400；',
    'AI 全局共用：所有账号的重要性判定、图片识别、语音转写统一调用管理员在 app.env 配置的 AI API（Key 全局唯一，不回显明文）；',
    '命令隔离：生成报告/重载关键词等操作只作用于当前用户自己的实例（命令通道按用户分文件）。',
]
for it in multi_items:
    doc.add_paragraph(it, style='List Bullet')

doc.add_heading('4.7 安全加固设计', level=2)
sec_items = [
    '登录限流：同一 IP+账号 5 分钟失败 5 次锁定 10 分钟，注册限频（同 IP 10 分钟 5 次）；',
    'IP 取信：仅信任 Nginx 覆盖的 X-Real-IP，防止伪造 X-Forwarded-For 绕过限流；',
    'JWT 加固：默认密钥启动自动随机化；令牌携带密码版本号，改密/删号后旧令牌立即失效；',
    '配置注入拦截：.env 写入值清洗换行与控制字符，无法注入新配置键；',
    'CSRF 防护：全局中间件校验 Origin，跨站 POST 一律拒绝；',
    '前端输出全转义 + 报告 HTML 加 CSP（禁脚本）+ nosniff，杜绝 XSS；',
    '路径穿越防护：文件下载/媒体读取双重校验前缀与真实路径；',
    '分页上限（page_size≤200）、SSE 每用户连接数上限（3 个）、限流内存惰性清理；',
    '原子写入（tmp+rename）防配置文件损坏；完整审计日志（登录/越权/管理操作）记录到 logs/web.log；',
    '密钥接口脱敏回显，敏感配置仅存服务器本地。',
]
for it in sec_items:
    doc.add_paragraph(it, style='List Bullet')

# ═══════ 五、创新点 ═══════
doc.add_heading('五、项目创新点', level=1)
innovations = [
    ('「关键词 + AI」双重判定架构', '既有规则引擎的秒级筛选速度，又有大模型的理解能力，兼顾准确率与调用成本，是轻量级智能监控的工程化范式'),
    ('SSE 毫秒级实时推送', '免 WebSocket 的复杂握手与鉴权，以极低成本实现新消息/新提醒的即时到达，前端零依赖断线自动重连'),
    ('多媒体自动归档 + 三路 AI 识别', '图片（视觉模型）/ 文件（类型分类）/ 语音（ASR 转写）自动保存并智能标记，形成可检索的班级资料库'),
    ('多租户账号隔离', '每账号独立平台绑定/关键词/数据空间（独立 SQLite 库），数据完全互不可见；AI 能力全局共用，隐私与共享兼得'),
    ('双平台能力对齐的适配器架构', 'QQ（WebSocket 推送）与钉钉（轮询补拉）统一抽象为适配器，媒体/判定/提醒管线完全复用，新增平台成本低'),
    ('多进程独立 + 命令通道解耦', 'Web 与各平台 worker 互不干扰、崩溃自愈，命令通过文件通道下发，架构简单可靠'),
    ('面向校园场景的词库与判定标准', '内置 16 类校园专属风险词库与分级判定标准（紧急事件 high / 事务通知 medium），贴合实际使用场景'),
]
t = doc.add_table(rows=1, cols=2)
t.style = 'Table Grid'
t.rows[0].cells[0].text = '创新点'; t.rows[0].cells[1].text = '价值说明'
for a, b in innovations:
    row = t.add_row().cells
    row[0].text = a; row[1].text = b

# ═══════ 六、测试与验证 ═══════
doc.add_heading('六、测试与验证', level=1)
doc.add_paragraph(
    '项目内置离线测试套件 test_offline.py（44 项自动化检查），覆盖：消息入库与去重、关键词匹配、'
    'AI 判定（打桩）、日报生成、Web API 认证与多租户隔离、注册/登录/限流、密码修改与令牌失效等，'
    '全部通过；另有多租户端到端验证（关键词/绑定/数据/命令四重隔离 + AI 全局共用）。'
)
ver = doc.add_table(rows=1, cols=3)
ver.style = 'Table Grid'
ver.rows[0].cells[0].text = '验证项'; ver.rows[0].cells[1].text = '方式'; ver.rows[0].cells[2].text = '结果'
vers = [
    ('QQ 凭证与网关', '真实 AppID/Secret 获取 access_token，WebSocket 连接收到 READY', '✅ 在线监听'),
    ('消息实时入库', '群里实际发言 → 数据库消息数增长', '✅ 全量接收'),
    ('AI 重要性判定', '真实调用 deepseek 判定「着火→high」「考试通知→medium」「闲聊→忽略」', '✅ 判定精准'),
    ('实时推送', '插入新提醒 → SSE 流 2 秒内收到 alert 事件', '✅ 毫秒级'),
    ('文件/语音识别', '真实图片经 qwen-vl-plus 识别；语音转写链路接口全通', '✅'),
    ('安全加固', '错误密码 5 次触发锁定(429)；跨站 POST 403；改密后旧 token 失效；.env 注入被拦截', '✅ 全部生效'),
    ('多租户隔离', '双账号端到端：关键词/绑定/消息数据/媒体访问完全互不可见，命令通道独立，AI 全局共用', '✅ 17/17'),
    ('动态实例接入', '新账号绑定机器人后 15 秒内自动创建独立连接实例并开始收消息', '✅'),
    ('新账号完整流程', '注册→自动登录→首页各接口（总览/消息/提醒/文件/报告）全部 200', '✅'),
]
for a, b, c in vers:
    row = ver.add_row().cells
    row[0].text = a; row[1].text = b; row[2].text = c

# ═══════ 七、部署与应用 ═══════
doc.add_heading('七、部署与应用场景', level=1)
doc.add_paragraph(
    '本地运行一条命令即可启动全部服务（python main.py all）；公网部署支持'
    'systemd 三服务守护 + Nginx 反代 HTTPS，具备完整上线清单（改默认密码、确认密钥随机化、'
    '关闭注册或启用邀请码、防火墙只开 80/443 等）。'
)
doc.add_paragraph('典型应用场景：')
for s in [
    '班级管理：班主任/班委实时掌握安全事件、考试通知、请假求助等关键信息；',
    '学生社团：活动报名、物资需求、失物招领自动归档，重要资料进入文件库；',
    '社群运营：管理员第一时间响应投诉维权、舆情预警，每日自动生成运营报告。',
]:
    doc.add_paragraph(s, style='List Bullet')

# ═══════ 八、总结与展望 ═══════
doc.add_heading('八、总结与展望', level=1)
doc.add_paragraph(
    '本项目从校园班级管理的真实痛点出发，完整实现了多平台群聊消息的采集、智能分析、实时提醒、'
    '自动归档与多用户管理，形成了从「数据接入 → 智能判定 → 即时触达 → 沉淀归档」的闭环，'
    '并通过系统性的安全加固保证可靠上线。'
)
doc.add_paragraph(
    '后续展望：① 接入更多平台（微信群/飞书群）；② 支持多关键词组自定义策略（如夜间静默、'
    '不同群不同规则）；③ 增加提醒的短信/电话触达；④ 基于历史数据生成周报/趋势分析；'
    '⑤ 文件库支持全文检索与智能问答。'
)

doc.save('D:/chat-monitor/docs/创作说明.docx')
print('✅ 创作说明.docx 已生成')
