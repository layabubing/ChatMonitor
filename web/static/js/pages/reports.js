/* 报告页：列表 + 模态预览（Esc/遮罩关闭） */
import { $, api, esc, toast, PLATFORM_NAMES } from '../util.js';
import { bindSeg, segValue, delegate, setLoading } from '../ui.js';

export function init() {
  bindSeg('repPlatform', load);
  $('repRefresh').addEventListener('click', load);
  $('repClosePreview').addEventListener('click', closePreview);
  $('repModal').addEventListener('click', (e) => { if (e.target.id === 'repModal') closePreview(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePreview(); });
  delegate('repList', { preview: (ds) => openPreview(ds.platform, ds.date) });
}

export async function load() {
  setLoading('repList', 3);
  const p = segValue('repPlatform');
  try {
    const d = await api(`/api/reports${p ? '?platform=' + p : ''}`);
    $('repList').innerHTML = d.items.length ? `<div class="rep-grid">${d.items.map((r) => `
      <div class="rep-card">
        <div class="meta" style="margin-bottom:8px">
          <span class="chip ${r.platform === 'qq' ? 'blue' : 'green'}">${PLATFORM_NAMES[r.platform] || esc(r.platform)}</span>
        </div>
        <div class="rep-date">${esc(r.date)}</div>
        <div class="rep-meta">消息 ${r.msg_count} 条 · 重要 ${r.important_count} 条</div>
        <div class="row-flex">
          <button class="btn sm primary" data-action="preview" data-platform="${esc(r.platform)}" data-date="${esc(r.date)}">在线预览</button>
          <a class="btn sm" href="/api/reports/${esc(r.platform)}/${esc(r.date)}/docx">下载 docx</a>
        </div>
      </div>`).join('')}</div>`
      : '<div class="card"><div class="empty">暂无报告，可在总览页点击「立即生成日报」</div></div>';
  } catch (e) {
    $('repList').innerHTML = `<div class="card"><div class="empty">${esc(e.message)}</div></div>`;
  }
}

async function openPreview(platform, date) {
  // 预检权限与存在性（注意：响应是 HTML，不能用 api() 的 r.json() 解析）
  const r = await fetch(`/api/reports/${platform}/${date}/html`);
  if (r.status === 401) { location.href = '/login'; return; }
  if (!r.ok) {
    let msg = '报告不存在或无法访问';
    try { msg = (await r.json()).error || msg; } catch { /* 非 JSON */ }
    toast(msg, true);
    return;
  }
  $('repPreviewTitle').textContent = `${PLATFORM_NAMES[platform] || platform} ${date} 日报`;
  $('repIframe').src = `/api/reports/${platform}/${date}/html`;
  $('repDownloadDocx').href = `/api/reports/${platform}/${date}/docx`;
  $('repModal').hidden = false;
}

function closePreview() {
  const modal = $('repModal');
  if (modal.hidden) return;
  modal.hidden = true;
  $('repIframe').src = 'about:blank';   // 释放 iframe 内容
}
