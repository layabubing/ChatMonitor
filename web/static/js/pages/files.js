/* 文件库：平台/分类/重要筛选 + 实时搜索(防抖) + 分页 + 重要标记（事件委托） */
import { $, api, esc, fmtTs, fmtSize, toast, debounce, PLATFORM_NAMES } from '../util.js';
import { bindSeg, segValue, delegate, setLoading, refillSelect } from '../ui.js';

const FILE_ICONS = { image: '🖼', document: '📄', table: '📊', slide: '📑', archive: '📦', audio: '🎵', video: '🎬', other: '📁' };
let page = 1;

export function init() {
  bindSeg('filePlatform', () => { page = 1; load(); });
  $('fileCategory').addEventListener('change', () => { page = 1; load(); });
  $('fileImportant').addEventListener('change', () => { page = 1; load(); });
  const liveSearch = debounce(() => { page = 1; load(); }, 300);
  $('fileQ').addEventListener('input', liveSearch);
  $('fileRefresh').addEventListener('click', load);
  $('filePrev').addEventListener('click', () => { if (page > 1) { page--; load(); } });
  $('fileNext').addEventListener('click', () => { page++; load(); });
  delegate('fileList', {
    'toggle-important': async (ds) => {
      try {
        await api(`/api/files/${ds.platform}/${ds.id}/important`, {
          method: 'POST', body: JSON.stringify({ important: ds.cur !== '1' }),
        });
        load();
      } catch (e) { toast(e.message, true); }
    },
  });
}

export async function load() {
  await loadCategories();
  await loadList();
}

async function loadCategories() {
  try {
    const d = await api('/api/files/categories');
    refillSelect($('fileCategory'), d.items, '全部分类');   // 保留已选分类
  } catch { /* 分类失败不阻塞列表 */ }
}

async function loadList() {
  setLoading('fileList', 5);
  const p = segValue('filePlatform');
  const cat = $('fileCategory').value;
  const imp = $('fileImportant').checked ? '&important=true' : '';
  const q = $('fileQ').value;
  try {
    const d = await api(`/api/files?platform=${p}&category=${encodeURIComponent(cat)}${imp}&q=${encodeURIComponent(q)}&page=${page}&page_size=50`);
    const totalPages = Math.max(1, Math.ceil(d.total / d.page_size));
    page = Math.min(page, totalPages);
    $('filePageInfo').textContent = `第 ${page}/${totalPages} 页 · 共 ${d.total} 个文件`;
    $('filePrev').disabled = page <= 1;
    $('fileNext').disabled = page >= totalPages;
    $('fileList').innerHTML = d.items.length ? d.items.map(renderFile).join('')
      : '<div class="empty">暂无文件（群里的图片/文件会自动保存到这里）</div>';
  } catch (e) {
    $('fileList').innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

function renderFile(f) {
  const raw = `/api/files/${f.platform}/${f.id}/raw`;
  const thumb = f.ftype === 'image'
    ? `<a href="${raw}" target="_blank" rel="noopener"><img src="${raw}" loading="lazy" alt=""></a>`
    : (FILE_ICONS[f.ftype] || '📁');
  return `
    <div class="li file-item ${f.important ? 'important' : ''}">
      <div class="file-thumb">${thumb}</div>
      <div class="li-main">
        <div class="file-name">${esc(f.orig_name)} ${f.important ? '<span class="chip amber">★ 重要</span>' : ''}</div>
        <div class="file-meta">${PLATFORM_NAMES[f.platform] || esc(f.platform)} · ${esc(f.category) || '未分类'} · ${fmtSize(f.size)} · ${fmtTs(f.ts)}</div>
        ${f.ai_desc ? `<div class="file-desc">🤖 ${esc(f.ai_desc)}</div>` : ''}
      </div>
      <div class="li-side">
        <a class="btn sm" href="${raw}" target="_blank" rel="noopener">预览</a>
        <a class="btn sm" href="${raw}" download="${esc(f.orig_name)}">下载</a>
        <button class="btn sm" data-action="toggle-important" data-platform="${esc(f.platform)}" data-id="${f.id}" data-cur="${f.important ? 1 : 0}">${f.important ? '取消重要' : '标重要'}</button>
      </div>
    </div>`;
}
