/* 提醒页：平台筛选 + 仅未读 + 标记已读；角标独立维护（任何页面都会刷新） */
import { $, api, esc, fmtTs, toast, PLATFORM_NAMES } from '../util.js';
import { bindSeg, segValue, delegate, setLoading } from '../ui.js';

const PRI_NAMES = { high: '高', medium: '中', low: '低' };

export function init() {
  bindSeg('alertPlatform', load);
  $('alertUnread').addEventListener('change', load);
  $('alertRefresh').addEventListener('click', () => { load(); updateBadge(); });
  $('alertAllRead').addEventListener('click', markAllRead);
  delegate('alertList', {
    read: async (ds) => {
      try {
        await api('/api/alerts/read', { method: 'POST', body: JSON.stringify({ ids: [+ds.id] }) });
        await Promise.all([load(), updateBadge()]);
      } catch (e) { toast(e.message, true); }
    },
  });
}

export async function load() {
  setLoading('alertList');
  const p = segValue('alertPlatform');
  const unread = $('alertUnread').checked;
  try {
    const d = await api(`/api/alerts?platform=${p}&unread=${unread}&page_size=100`);
    $('alertList').innerHTML = d.items.length ? d.items.map(renderAlert).join('')
      : `<div class="empty">${unread ? '没有未读提醒 🎉' : '暂无重要提醒'}</div>`;
  } catch (e) {
    $('alertList').innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

/** 未读角标：轻量请求（page_size=1 只取 total），供顶栏与 SSE 事件调用 */
export async function updateBadge() {
  try {
    const d = await api('/api/alerts?unread=true&page_size=1');
    const badge = $('alertBadge');
    badge.hidden = !d.total;
    badge.textContent = d.total > 99 ? '99+' : d.total;
  } catch { /* 角标失败静默 */ }
}

/** "当前筛选全部已读"：作用于当前选中的平台筛选范围 */
async function markAllRead() {
  const p = segValue('alertPlatform');
  try {
    const r = await api('/api/alerts/read', { method: 'POST', body: JSON.stringify(p ? { platform: p } : {}) });
    toast(`已标记 ${r.updated} 条为已读`);
    await Promise.all([load(), updateBadge()]);
  } catch (e) { toast(e.message, true); }
}

const PRI_CHIP = { high: 'red', medium: 'amber', low: 'green' };

function renderAlert(a) {
  return `
    <div class="li alert-item ${a.is_read ? '' : 'unread'}">
      <div class="li-main">
        <div class="meta">
          <span class="chip ${PRI_CHIP[a.priority] || ''}">${PRI_NAMES[a.priority] ? PRI_NAMES[a.priority] + '优先级' : esc(a.priority)}</span>
          <span>${PLATFORM_NAMES[a.platform] || esc(a.platform)}</span>
          <span>${esc(a.group_name) || '群'} · ${esc(a.sender) || '匿名'}</span>
          <span>${fmtTs(a.ts)}</span>
          ${a.is_read ? '' : '<span class="chip blue">未读</span>'}
        </div>
        <div style="margin-top:4px">${esc(a.content)}</div>
        ${a.reason ? `<div class="reason">原因：${esc(a.reason)}</div>` : ''}
        ${a.suggestion ? `<div class="sugg">💡 建议：${esc(a.suggestion)}</div>` : ''}
      </div>
      ${a.is_read ? '' : `<div class="li-side"><button class="btn sm read-btn" data-action="read" data-id="${a.id}">标已读</button></div>`}
    </div>`;
}
