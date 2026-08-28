/* 总览仪表盘：跨平台汇总条 + 平台状态卡 + 最新未读提醒 + 新用户引导 */
import { $, api, esc, fmtTs, toast, PLATFORM_NAMES } from '../util.js';
import { delegate, setLoading } from '../ui.js';

let nav = () => {};
let setMsgPlatform = () => {};

export function init(ctx) {
  nav = ctx.navigate;
  setMsgPlatform = ctx.setMsgPlatform;
  const actions = {
    'goto-messages': (ds) => { setMsgPlatform(ds.platform); nav('messages'); },
    'goto-alerts': () => nav('alerts'),
    'gen-report': async (ds, el) => {
      el.disabled = true;
      try {
        await api(`/api/platforms/${ds.platform}/command`, { method: 'POST', body: JSON.stringify({ cmd: 'generate_report' }) });
        toast('已下发日报生成命令，完成后将实时通知你');
      } catch (e) { toast(e.message, true); }
      finally { setTimeout(() => { el.disabled = false; }, 1500); }
    },
    'goto-settings': () => nav('settings'),
  };
  delegate('overviewGrid', actions);
  delegate('overviewGuide', actions);
  delegate('statStrip', actions);
  delegate('ovAlerts', actions);
}

export async function load() {
  setLoading('statStrip', 1);
  setLoading('overviewGrid', 2);
  try {
    const [data, unread] = await Promise.all([
      api('/api/overview'),
      api('/api/alerts?unread=true&page_size=3').catch(() => ({ items: [], total: 0 })),
    ]);
    const entries = Object.entries(data);
    renderStrip(entries, unread.total);
    renderCards(entries);
    renderRecentAlerts(unread.items);
    renderGuide(entries);
  } catch (e) {
    $('statStrip').innerHTML = '';
    $('overviewGrid').innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

/** 跨平台汇总条 */
function renderStrip(entries, unreadTotal) {
  const sum = (k) => entries.reduce((acc, [, ov]) => acc + (ov[k] || 0), 0);
  const running = entries.filter(([, ov]) => ov.running).length;
  $('statStrip').innerHTML = `
    <div class="stat-card"><div class="v">${sum('msg_total')}</div><div class="k">累计消息</div></div>
    <div class="stat-card"><div class="v">${sum('today_messages')}</div><div class="k">今日消息</div></div>
    <div class="stat-card accent clickable" data-action="goto-alerts" title="查看提醒">
      <div class="v">${unreadTotal}</div><div class="k">未读提醒 ›</div></div>
    <div class="stat-card"><div class="v">${running}/${entries.length}</div><div class="k">平台运行中</div></div>`;
}

function renderCards(entries) {
  $('overviewGrid').innerHTML = entries.map(([p, ov]) => `
    <div class="pcard">
      <div class="pname">
        <a href="javascript:void 0" data-action="goto-messages" data-platform="${p}">${PLATFORM_NAMES[p] || p}</a>
        <span class="chip ${ov.running ? 'green' : 'red'}">${ov.running ? '● 运行中' : '● 已停止'}</span>
      </div>
      <div class="stats">
        <div class="stat"><b>${ov.msg_total}</b><span>累计消息</span></div>
        <div class="stat"><b>${ov.today_messages}</b><span>今日消息</span></div>
        <div class="stat clickable" data-action="goto-alerts"><b>${ov.alert_unread}</b><span>未读提醒</span></div>
      </div>
      <div class="last-report">最近报告：${ov.last_report ? esc(ov.last_report.date) : '暂无'}</div>
      <div class="actions">
        <button class="btn sm" data-action="gen-report" data-platform="${p}">立即生成日报</button>
      </div>
    </div>`).join('');
}

/** 最新 3 条未读提醒预览 */
function renderRecentAlerts(items) {
  const card = $('ovAlertsCard');
  if (!items.length) { card.hidden = true; return; }
  card.hidden = false;
  $('ovAlerts').innerHTML = items.map((a) => `
    <div class="li" data-action="goto-alerts" style="cursor:pointer">
      <div class="li-main">
        <div class="meta">
          <span class="chip ${a.priority === 'high' ? 'red' : a.priority === 'medium' ? 'amber' : 'green'}">${a.priority}</span>
          <span>${PLATFORM_NAMES[a.platform] || esc(a.platform)}</span>
          <span>${esc(a.group_name) || '群'} · ${esc(a.sender) || '匿名'}</span>
          <span>${fmtTs(a.ts)}</span>
        </div>
        <div style="margin-top:3px">${esc(a.content).slice(0, 120)}</div>
      </div>
    </div>`).join('');
}

/** 双平台都没消息时显示上手引导 */
function renderGuide(entries) {
  const allEmpty = entries.every(([, ov]) => !ov.msg_total);
  $('overviewGuide').innerHTML = allEmpty ? `
    <div class="guide-card">
      <h3>👋 三步开始监控你的群聊</h3>
      <ol>
        <li>前往 <b>设置 → 平台绑定</b>，填入 QQ 或钉钉机器人凭证并启用</li>
        <li>在 <b>设置 → 关键词库</b> 维护你关心的关键词（命中后才交 AI 判定）</li>
        <li>回到本页确认状态为「运行中」，日报将于每天定时自动生成</li>
      </ol>
      <button class="btn primary" data-action="goto-settings">去绑定平台</button>
    </div>` : '';
}
