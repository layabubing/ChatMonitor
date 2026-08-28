/* 消息页：平台/群筛选 + 实时搜索(防抖) + 分页 + 媒体预览（事件委托，无 inline onclick） */
import { $, api, esc, fmtTs, debounce } from '../util.js';
import { bindSeg, segValue, setSeg, setLoading, refillSelect } from '../ui.js';

let page = 1;

export function init() {
  bindSeg('msgPlatform', () => { page = 1; loadGroups(); load(); });
  const liveSearch = debounce(() => { page = 1; load(); }, 300);
  $('msgQ').addEventListener('input', liveSearch);
  $('msgGroup').addEventListener('change', () => { page = 1; load(); });
  $('msgRefresh').addEventListener('click', () => { loadGroups(); load(); });
  $('msgPrev').addEventListener('click', () => { if (page > 1) { page--; load(); } });
  $('msgNext').addEventListener('click', () => { page++; load(); });
}

/** 供其他页面跳转时预选平台（如总览卡片点击） */
export function setPlatform(p) {
  if (segValue('msgPlatform') === p) return;
  setSeg('msgPlatform', p);
  page = 1;
}

/** SSE 新消息事件：仅当消息页可见且平台匹配时刷新（保持滚动位置） */
export function onNewMessage(platform, isActive) {
  if (!isActive || segValue('msgPlatform') !== platform) return;
  const y = window.scrollY;
  load().then(() => window.scrollTo(0, y));
}

async function loadGroups() {
  try {
    const g = await api(`/api/groups?platform=${segValue('msgPlatform')}`);
    refillSelect($('msgGroup'), g.items, '全部群');   // 重建选项时保留已选群
  } catch { /* 群列表失败不阻塞消息加载 */ }
}

export async function load() {
  setLoading('msgList', 5);
  const p = segValue('msgPlatform');
  const g = $('msgGroup').value;
  const q = $('msgQ').value;
  try {
    const d = await api(`/api/messages?platform=${p}&group=${encodeURIComponent(g)}&q=${encodeURIComponent(q)}&page=${page}&page_size=50`);
    const totalPages = Math.max(1, Math.ceil(d.total / d.page_size));
    page = Math.min(page, totalPages);
    $('msgPageInfo').textContent = `第 ${page}/${totalPages} 页 · 共 ${d.total} 条`;
    $('msgPrev').disabled = page <= 1;
    $('msgNext').disabled = page >= totalPages;
    $('msgList').innerHTML = d.items.length ? d.items.map(renderMsg).join('') : '<div class="empty">暂无消息</div>';
  } catch (e) {
    $('msgList').innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

function renderMsg(m) {
  const media = (m.media_urls || [])
    .filter((x) => typeof x === 'string' && (x.startsWith('media/') || x.startsWith('users/')))
    .map(renderMedia).join('');
  return `
    <div class="li msg-item ${m.is_important ? 'important' : ''}">
      <div class="li-main">
        <div class="meta">
          <span class="sender">${esc(m.sender) || '匿名'}</span>
          <span class="chip">${esc(m.group_name) || '群'}</span>
          <span class="chip blue">${esc(m.msg_type)}</span>
          <span title="${new Date(m.ts > 1e12 ? m.ts : m.ts * 1000).toLocaleString()}">${fmtTs(m.ts)}</span>
        </div>
        <div class="content">${esc(m.content) || '(无文本)'}</div>
        ${media ? `<div class="msg-media">${media}</div>` : ''}
      </div>
    </div>`;
}

function renderMedia(path) {
  const url = '/api/media/raw?path=' + encodeURIComponent(path);
  const low = path.toLowerCase();
  if (/\.(jpg|jpeg|png|gif|webp|bmp)$/.test(low)) {
    return `<a href="${url}" target="_blank" rel="noopener"><img src="${url}" loading="lazy" alt=""></a>`;
  }
  if (/\.(mp4|mov|3gp|webm|m4v)$/.test(low)) {
    return `<video src="${url}" controls preload="metadata"></video>`;
  }
  const name = path.split('/').pop() || '附件';
  return `<a class="btn sm file-link" href="${url}" target="_blank" rel="noopener">📎 ${esc(name)}</a>`;
}
