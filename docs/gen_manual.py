# -*- coding: utf-8 -*-
"""生成《使用说明》docx：聊天智能分析助手（ChatMonitor）"""
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

ACCENT = RGBColor(0x2F, 0x6B, 0xFF)
DARK = RGBColor(0x33, 0x33, 0x33)


def set_cn(style_name, size=11, bold=False, color=DARK, font='微软雅黑'):
    doc.styles[style_name].font.name = font
    doc.styles[style_name].font.size = Pt(size)
    doc.styles[style_name].font.bold = bold
    doc.styles[style_name].font.color.rgb = color
    doc.styles[style_name]._element.rPr.rFonts.set(qn('w:eastAsia'), font)


doc = Document()
for s in doc.sections:
    s.top_margin, s.bottom_margin = Cm(2.2), Cm(2.2)
    s.left_margin, s.right_margin = Cm(2.5), Cm(2.5)

set_cn('Normal', 11)
set_cn('Heading 1', 16, True, ACCENT)
set_cn('Heading 2', 13, True, RGBColor(0x1F, 0x4E, 0xB8))
set_cn('Heading 3', 11.5, True)

# ═══════ 封面 ═══════
for _ in range(5):
    doc.add_paragraph()
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run('聊天智能分析助手\n使用说明'); r.font.size = Pt(26); r.font.bold = True; r.font.color.rgb = ACCENT
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run('—— ChatMonitor 用户手册 ——'); r.font.size = Pt(13); r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
doc.add_paragraph()
for line in ['版本：v1.0', '日期：2026 年 8 月']:
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(line); r.font.size = Pt(12)
doc.add_page_break()

# ═══════ 一、系统简介 ═══════
doc.add_heading('一、系统简介', level=1)
doc.add_paragraph(
    '聊天智能分析助手（ChatMonitor）是一款多平台群聊信息智能监控与分析工具。'
    '接入 QQ 群 / 钉钉群后，系统自动抓取群内消息，智能识别重要信息并实时提醒，'
    '每日自动生成报告，同时自动保存聊天中的图片、文件、语音并 AI 分类归档。'
)
doc.add_paragraph('系统提供 Web 管理界面，打开浏览器即可使用，支持多人注册登录；每个账号拥有独立空间（绑定/关键词/数据互不可见），AI 能力全局共用。')

# ═══════ 二、快速开始 ═══════
doc.add_heading('二、快速开始', level=1)
doc.add_heading('2.1 本地启动', level=2)
steps = [
    '安装 Python 3.11 与环境依赖：',
    '配置 configs/app.env（管理员账号、JWT 密钥、AI Key）与 configs/qq.env / dingtalk.env（平台凭证）；',
    '启动：python main.py all（或分别 main.py web / qq / dingtalk）；',
    '浏览器打开 http://127.0.0.1:8001，用配置的管理员账号登录。',
]
doc.add_paragraph(''.join(steps))
code = doc.add_paragraph()
r = code.add_run('python -m venv .venv\n.venv/Scripts/pip install -r requirements.txt\npython main.py all')
r.font.name = 'Consolas'; r.font.size = Pt(10); r.font.color.rgb = RGBColor(0x1F, 0x4E, 0xB8)

doc.add_heading('2.2 公网部署', level=2)
doc.add_paragraph(
    '按 deploy/DEPLOY.md 操作：将项目部署到云服务器（Ubuntu 22.04），'
    '通过 systemd 守护三个服务、Nginx 反向代理对外提供 HTTPS 访问。'
)

# ═══════ 三、平台账号接入 ═══════
doc.add_heading('三、平台账号接入', level=1)
doc.add_paragraph('详细图文步骤见 docs/ACCOUNT_SETUP.md。以下为要点速览：')

doc.add_heading('3.1 接入 QQ 群', level=2)
for s in [
    '在 QQ 开放平台（q.qq.com）创建机器人，记录 AppID 与 AppSecret；',
    '机器人配置中开启「接收所有消息」（全量模式），并发布正式版本；',
    '在 QQ 客户端将机器人添加到目标群（需群主操作），进群后在群设置中将「机器人可获取的群聊消息范围」设为「获取群内全部消息」；',
    '将 AppID/AppSecret 填入 configs/qq.env（或 Web 设置页在线绑定），保存并重启 worker；',
    '群 ID 可留空（监控所有群），需要精确监控时从消息页获取 group openid 回填。',
]:
    doc.add_paragraph(s, style='List Number')

doc.add_heading('3.2 接入钉钉群', level=2)
for s in [
    '在钉钉开放平台（open.dingtalk.com）创建企业内部应用，记录 AppKey / AppSecret；',
    '在权限管理申请 qyapi_chat_read（读取群消息）权限；',
    '群主/管理员在目标群授权应用，获取群 chatId；',
    '填入 configs/dingtalk.env（或 Web 设置页绑定），启用后保存重启。',
]:
    doc.add_paragraph(s, style='List Number')

# ═══════ 四、Web 界面使用 ═══════
doc.add_heading('四、Web 界面使用指南', level=1)

doc.add_heading('4.1 登录与注册', level=2)
doc.add_paragraph(
    '打开系统首页进入登录页。管理员账号由部署者提供；若系统开放注册（REGISTER_OPEN=true），'
    '可切换到「注册」页签创建普通用户账号（需通过审核/邀请码时按要求填写）。'
)

doc.add_heading('4.2 总览页', level=2)
doc.add_paragraph(
    '展示各平台运行状态（worker 在线/心跳）、今日消息数、提醒数、最近报告等信息，'
    '每 5 秒自动刷新。可在此手动触发「生成报告」「重载关键词」等操作（作用于自己的账号）。'
)

doc.add_heading('4.3 消息页', level=2)
doc.add_paragraph(
    '按平台（QQ/钉钉）切换查看群聊消息列表，支持按群筛选、关键词搜索、分页浏览。'
    '图片消息显示缩略图（点击看原图），视频可内嵌播放，语音消息显示转写文本。'
    '新消息通过 SSE 实时推送，无需手动刷新。'
)

doc.add_heading('4.4 提醒页', level=2)
doc.add_paragraph(
    '集中展示系统识别出的重要提醒，按优先级（high/medium/low）区分，'
    '每条包含：触发消息、判定原因、处置建议（动作/责任人/优先级）。'
    '新提醒实时弹出提示并更新角标，支持按未读筛选。'
)

doc.add_heading('4.5 报告页', level=2)
doc.add_paragraph(
    '查看每日自动生成的图文报告（docx + html），支持在线预览与下载；'
    '可在总览页手动触发当天报告生成（只生成自己账号的报告）。报告底部注明使用的 AI 模型。'
)

doc.add_heading('4.6 文件库页', level=2)
doc.add_paragraph(
    '展示【你账号下】群聊中自动保存的图片/文件/语音：缩略图预览、在线预览/下载、'
    '按平台/分类/重要状态筛选、关键词搜索；AI 已自动识别内容并为重要资料打上「★ 重要」标记，'
    '可手动更正。重要文件自动生成提醒（同样只作用于自己的账号）。'
)

doc.add_heading('4.7 设置页', level=2)
for s in [
    '我的账号（所有用户）：修改昵称、修改密码（需验证旧密码，改后重新登录）；',
    '我的 QQ / 钉钉账号绑定（所有用户）：填写【你自己】的平台凭证（AppID/Secret）→ 测试连接 → 保存并重启生效；每个账号绑定自己的机器人，互不可见；绑定保存后 15 秒内 worker 自动接入（无需手动重启服务）；',
    '我的关键词库（所有用户）：按类别增删【你自己】的关键词，添加即自动保存并实时生效；',
    'AI 信息（所有用户可见）：展示系统全局共用的 AI 模型（deepseek-v4-flash-0731 / qwen-vl-plus / paraformer-v2），由部署者统一配置。',
]:
    doc.add_paragraph(s, style='List Bullet')

# ═══════ 五、关键词管理 ═══════
doc.add_heading('五、关键词管理（重点·每账号独立）', level=1)
doc.add_paragraph(
    '关键词库是系统智能判定的第一级过滤器，位于设置页「我的关键词库」——'
    '【每个账号都有自己的关键词库】，完全独立、互不影响（多租户隔离）。'
    '系统预置了 16 类共 288 个校园高频风险词模板（紧急求助、安全应急、健康医疗、失联求助、'
    '财物丢失、学习考试、校园设施、食品安全、交通出行、网络信息、人际关系、情绪心理、'
    '投诉维权、活动事务、气象灾害等），新注册账号自动获得，可在其基础上按需增删。'
)
doc.add_paragraph('使用要点：')
for s in [
    '在对应类别输入框添加新词，点击「添加」即自动保存并生效（无需手动点保存）；',
    '你保存的关键词只作用于【你自己的账号】：你的消息用你的词库判定，不影响其他账号；',
    '关键词越精准越好，避免「食堂」「考试」这类高频日常词造成误报（系统已剔除大部分）；',
    '命中关键词的消息会进入 AI 二次判定（AI 全局共用部署者配置的模型），闲聊会被自动过滤；',
    '保存关键词后系统自动对当天历史消息「补判定」，新词不会遗漏已发消息。',
]:
    doc.add_paragraph(s, style='List Bullet')

# ═══════ 六、多租户与权限 ═══════
doc.add_heading('六、多租户账号隔离', level=1)
doc.add_paragraph(
    '系统为每个账号提供完全独立的监控空间（类似 QQ 的账号体系）：'
)
for s in [
    '独立绑定：每个账号在设置页绑定【自己】的 QQ/钉钉凭证，A 账号的机器人/群 B 账号完全不可见；',
    '独立数据：消息、提醒、报告、文件、媒体（图片/文件/语音）按账号分别存储，跨账号不可访问；',
    '独立关键词：见第五章；',
    '独立操作：生成报告、重载关键词等只作用于自己的实例；绑定保存后 15 秒内自动接入独立连接；',
    '全局共用：AI 模型与 API Key 由部署者统一配置（app.env），所有账号共用，不占用各自资源。',
]:
    doc.add_paragraph(s, style='List Bullet')
doc.add_paragraph(
    '管理员账号与普通账号的数据隔离规则相同（均为独立空间）；'
    '管理员额外拥有系统级权限（重置任意用户密码等）。'
)

# ═══════ 七、常见问题 ═══════
doc.add_heading('七、常见问题排查', level=1)
faq = [
    ('收不到群消息', '① 机器人是否已发布正式版？② 是否开启「接收所有消息」？③ 机器人是否在群里？④ 总览页 worker 是否"运行中"？'),
    ('只收到 @ 机器人的消息', '未开启全量模式：群设置 → 群机器人 → 消息范围 → 「获取群内全部消息」。'),
    ('测试连接失败', '检查 AppID/AppSecret 是否复制完整（注意 AppSecret 开头为 sk- 等前缀）、平台是否已发布。'),
    ('关键词加了不生效', '确认输入后点了「添加」（自动保存）；查看词库文件是否更新；等待 worker 重载（命令通道自动触发）。'),
    ('有关键词消息却没提醒', '属正常现象：AI 二次判定认为该消息不重要（如测试消息/闲聊）会被过滤；真实紧急事件会正常提醒。'),
    ('日报为空', '当天群内无消息，或关键词未命中任何重要信息；可在总览页手动生成查看。'),
    ('图片/文件无法预览', '文件库点「预览」新窗口打开（图片/PDF 直接看）；点「下载」保存；浏览器需允许新窗口。'),
    ('忘记密码', '在设置页用旧密码修改；管理员可在登录后重置其他用户密码。'),
]
t = doc.add_table(rows=1, cols=2)
t.style = 'Table Grid'
t.rows[0].cells[0].text = '问题'; t.rows[0].cells[1].text = '排查方法'
for a, b in faq:
    row = t.add_row().cells
    row[0].text = a; row[1].text = b

# ═══════ 八、安全注意事项 ═══════
doc.add_heading('八、安全与合规提醒', level=1)
for s in [
    '上线前务必修改默认管理员密码；确认 JWT_SECRET 已随机化（启动自动处理）；',
    '公网部署建议关闭开放注册（REGISTER_OPEN=false）或启用邀请码；HTTPS 部署设置 COOKIE_SECURE=true；',
    '平台凭证与 AI Key 仅存服务器本地，切勿提交到公开仓库；',
    '遵守 QQ/钉钉平台服务协议，仅监控你有权访问的群，控制使用频率；',
    '定期备份 data/（含 users.db 与 data/users/ 各账号数据）、configs/、reports/ 目录。',
]:
    doc.add_paragraph(s, style='List Bullet')

doc.save('D:/chat-monitor/docs/使用说明.docx')
print('✅ 使用说明.docx 已生成')
