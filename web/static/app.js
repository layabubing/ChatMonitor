/* 仪表盘前端逻辑 */
const $ = (id) => document.getElementById(id);
const PLATFORM_NAMES = { qq: 'QQ', dingtalk: '钉钉' };

let msgPage = 1;
let filePage = 1;
let kwData = {};
let lastReportPreview = null;
let ROLE = 'user';   // admin / user

function toast(msg, isErr = false) {
  const t = $('toast');
  t.textContent = msg;
  t.className = isErr ? 'show err' : 'show';
  setTimeout(() => { t.className = ''; }, 2600);
}

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (r.status === 401) { location.href = '/login'; throw new Error('未登录'); }
  if (r.status === 403) { throw new Error('没有权限执行此操作'); }
  if (!r.ok) {
    let msg = '请求失败';
    try { msg = (await r.json()).error || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}

// ── 平台切换键（segmented control） ──
function bindSeg(segId, onChange) {
  const seg = $(segId);
  seg.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
    seg.querySelectorAll('button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    onChange(b.dataset.p);
  }));
}
function segValue(segId) {
  const active = $(segId).querySelector('button.active');
  return active ? active.dataset.p : '';
}

// ── 登录态与角色 ──
async function checkMe() {
  try {
    const me = await api('/api/me');
    ROLE = me.role || 'user';
    $('who').textContent = `${me.nickname || me.username}${ROLE === 'admin' ? '（管理员）' : ''}`;
    // 设置页对所有用户开放（个人中心）；管理员可看全部
    document.querySelectorAll('.tab[data-page="settings"]').forEach(t => t.style.display = '');
    loadSettings();
  } catch { location.href = '/login'; }
}

// ── 选项卡 ──
// ── 选项卡（刷新记住当前页并加载对应数据） ──
function loadPageData(page) {
  if (page === 'messages') { loadGroups(); loadMessages(); }
  if (page === 'reports') loadReports();
  if (page === 'alerts') loadAlerts();
  if (page === 'files') { loadFileCategories(); loadFiles(); }
  if (page === 'settings') loadSettings();
}
function initTabs() {
  const saved = localStorage.getItem('cm_tab') || 'overview';
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.page === saved);
  });
  document.querySelectorAll('.page').forEach(p => {
    p.classList.toggle('active', p.id === 'page-' + saved);
  });
  if (!document.querySelector('.page.active')) {
    $('page-overview').classList.add('active');
    document.querySelector('.tab[data-page="overview"]').classList.add('active');
    loadPageData('overview');
  } else {
    loadPageData(saved);
  }
}
initTabs();
document.querySelectorAll('.tab').forEach(t => t.addEventListener('click', () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  $('page-' + t.dataset.page).classList.add('active');
  localStorage.setItem('cm_tab', t.dataset.page);
  if (t.dataset.page === 'messages') loadGroups();
  if (t.dataset.page === 'reports') loadReports();
  if (t.dataset.page === 'alerts') loadAlerts();
  if (t.dataset.page === 'files') { loadFileCategories(); loadFiles(); }
  if (t.dataset.page === 'settings') loadSettings();
}));

$('logout').addEventListener('click', async () => { await api('/api/logout', { method: 'POST' }); location.href = '/login'; });

// ── 总览 ──
async function loadOverview() {
  try {
    const data = await api('/api/overview');
    $('overviewGrid').innerHTML = Object.entries(data).map(([p, ov]) => `
      <div class="pcard">
        <div class="pname">${PLATFORM_NAMES[p] || p}
          <span class="badge ${ov.running ? 'run' : 'stop'}">${ov.running ? '运行中' : '已停止'}</span>
        </div>
        <div class="stats">
          <div class="stat"><b>${ov.msg_total}</b><span>累计消息</span></div>
          <div class="stat"><b>${ov.today_messages}</b><span>今日消息</span></div>
          <div class="stat"><b>${ov.alert_unread}</b><span>未读提醒</span></div>
        </div>
        <div class="last-report">最近报告：${ov.last_report ? ov.last_report.date : '暂无'}</div>
        <div class="actions">
          <button class="btn sm" onclick="cmd('${p}','generate_report')">生成报告</button>
          <button class="btn sm" onclick="cmd('${p}','reload_keywords')">重载关键词</button>
        </div>
      </div>`).join('');
  } catch (e) { toast(e.message, true); }
}

async function cmd(platform, cmd) {
  try {
    await api(`/api/platforms/${platform}/command`, { method: 'POST', body: JSON.stringify({ cmd }) });
    toast(`已下发命令：${cmd}`);
  } catch (e) { toast(e.message, true); }
}

// ── 消息 ──
async function loadGroups() {
  const p = segValue('msgPlatform');
  try {
    const g = await api(`/api/groups?platform=${p}`);
    const sel = $('msgGroup');
    sel.innerHTML = '<option value="">全部群</option>' + g.items.map(x => `<option>${esc(x)}</option>`).join('');
  } catch {}
}

bindSeg('msgPlatform', () => { msgPage = 1; loadGroups(); loadMessages(); });
$('msgSearch').addEventListener('click', () => { msgPage = 1; loadMessages(); });
$('msgQ').addEventListener('keydown', e => { if (e.key === 'Enter') { msgPage = 1; loadMessages(); } });
$('msgPrev').addEventListener('click', () => { if (msgPage > 1) { msgPage--; loadMessages(); } });
$('msgNext').addEventListener('click', () => { msgPage++; loadMessages(); });

async function loadMessages() {
  const p = segValue('msgPlatform'), g = $('msgGroup').value, q = $('msgQ').value;
  try {
    const d = await api(`/api/messages?platform=${p}&group=${encodeURIComponent(g)}&q=${encodeURIComponent(q)}&page=${msgPage}&page_size=50`);
    const totalPages = Math.max(1, Math.ceil(d.total / d.page_size));
    msgPage = Math.min(msgPage, totalPages);
    $('msgPageInfo').textContent = `第 ${msgPage}/${totalPages} 页 · 共 ${d.total} 条`;
    $('msgPrev').disabled = msgPage <= 1;
    $('msgNext').disabled = msgPage >= totalPages;
    $('msgList').innerHTML = d.items.length ? d.items.map(m => {
      // 本地保存的媒体 → 小图预览（点击新窗口看原图；多租户路径 media/ 或 users/{username}/media/）
      const mediaHtml = (m.media_urls || []).filter(x => typeof x === 'string' && (x.startsWith('media/') || x.startsWith('users/')))
        .map(p => {
          const url = '/api/media/raw?path=' + encodeURIComponent(p);
          const low = p.toLowerCase();
          if (low.match(/\.(jpg|jpeg|png|gif|webp|bmp)$/)) {
            return `<a href="${url}" target="_blank"><img src="${url}" loading="lazy" style="max-width:64px;max-height:64px;border-radius:4px;margin:4px 4px 0 0;object-fit:cover;display:inline-block"></a>`;
          }
          if (low.match(/\.(mp4|mov|3gp|webm|m4v)$/)) {
            return `<video src="${url}" controls preload="metadata" style="max-width:160px;max-height:96px;border-radius:4px;margin:4px 4px 0 0;background:#000;display:block"></video>`;
          }
          return `<a class="btn sm" href="${url}" target="_blank" style="margin-top:6px">📎 ${esc(p.split('/').pop())}</a>`;
        }).join('');
      return `
      <div class="msg-item ${m.is_important ? 'important' : ''}">
        <div class="msg-head">
          <span class="sender">${esc(m.sender) || '匿名'}</span>
          <span class="grp">${esc(m.group_name) || '群'}</span>
          <span class="type">${m.msg_type}</span>
          <span>${fmtTs(m.ts)}</span>
        </div>
        <div class="msg-content">${esc(m.content) || '(无文本)'}</div>
        ${mediaHtml}
      </div>`;
    }).join('') : '<div class="empty">暂无消息</div>';
  } catch (e) { toast(e.message, true); }
}

// ── 文件库 ──
const FILE_ICONS = { image: '🖼', document: '📄', table: '📊', slide: '📑', archive: '📦', audio: '🎵', video: '🎬', other: '📁' };

async function loadFileCategories() {
  try {
    const d = await api('/api/files/categories');
    const sel = $('fileCategory');
    sel.innerHTML = '<option value="">全部分类</option>' + d.items.map(x => `<option>${esc(x)}</option>`).join('');
  } catch {}
}

bindSeg('filePlatform', () => { filePage = 1; loadFiles(); });
$('fileCategory').addEventListener('change', () => { filePage = 1; loadFiles(); });
$('fileImportant').addEventListener('change', () => { filePage = 1; loadFiles(); });
$('fileSearch').addEventListener('click', () => { filePage = 1; loadFiles(); });
$('fileQ').addEventListener('keydown', e => { if (e.key === 'Enter') { filePage = 1; loadFiles(); } });
$('filePrev').addEventListener('click', () => { if (filePage > 1) { filePage--; loadFiles(); } });
$('fileNext').addEventListener('click', () => { filePage++; loadFiles(); });

async function loadFiles() {
  const p = segValue('filePlatform'), cat = $('fileCategory').value,
        imp = $('fileImportant').checked ? '&important=true' : '', q = $('fileQ').value;
  try {
    const d = await api(`/api/files?platform=${p}&category=${encodeURIComponent(cat)}${imp}&q=${encodeURIComponent(q)}&page=${filePage}&page_size=50`);
    const totalPages = Math.max(1, Math.ceil(d.total / d.page_size));
    filePage = Math.min(filePage, totalPages);
    $('filePageInfo').textContent = `第 ${filePage}/${totalPages} 页 · 共 ${d.total} 个文件`;
    $('filePrev').disabled = filePage <= 1;
    $('fileNext').disabled = filePage >= totalPages;
    $('fileList').innerHTML = d.items.length ? d.items.map(f => {
      const isImg = f.ftype === 'image';
      return `
      <div class="file-item ${f.important ? 'important' : ''}">
        <div class="file-thumb">${isImg ? `<a href="/api/files/${f.platform}/${f.id}/raw" target="_blank"><img src="/api/files/${f.platform}/${f.id}/raw" loading="lazy" style="width:28px;height:28px;object-fit:cover;border-radius:4px;display:block"></a>` : FILE_ICONS[f.ftype] || '📁'}</div>
        <div class="file-body">
          <div class="file-name">${esc(f.orig_name)} ${f.important ? '<span class="tag-imp">★ 重要</span>' : ''}</div>
          <div class="file-meta">${PLATFORM_NAMES[f.platform] || f.platform} · ${f.category || '未分类'} · ${fmtSize(f.size)} · ${fmtTs(f.ts)}</div>
          ${f.ai_desc ? `<div class="file-desc">🤖 ${esc(f.ai_desc)}</div>` : ''}
        </div>
        <div class="file-actions">
          <a class="btn sm" href="/api/files/${f.platform}/${f.id}/raw" target="_blank">预览</a>
          <a class="btn sm" href="/api/files/${f.platform}/${f.id}/raw" download="${esc(f.orig_name)}">下载</a>
          <button class="btn sm" onclick="toggleFileImp(${f.id},${f.important?1:0},'${f.platform}')">${f.important ? '取消重要' : '标重要'}</button>
        </div>
      </div>`;
    }).join('') : '<div class="empty">暂无文件（群里的图片/文件会自动保存到这里）</div>';
  } catch (e) { toast(e.message, true); }
}

async function toggleFileImp(fid, cur, platform) {
  try {
    await api(`/api/files/${platform}/${fid}/important`, { method: 'POST', body: JSON.stringify({ important: !cur }) });
    loadFiles();
  } catch (e) { toast(e.message, true); }
}

function fmtSize(n) {
  if (!n) return '0B';
  if (n < 1024) return n + 'B';
  if (n < 1048576) return (n / 1024).toFixed(1) + 'KB';
  return (n / 1048576).toFixed(1) + 'MB';
}

// ── 报告 ──
bindSeg('repPlatform', loadReports);
$('repRefresh').addEventListener('click', loadReports);
$('repClosePreview').addEventListener('click', () => { $('repPreview').style.display = 'none'; });

async function loadReports() {
  const p = segValue('repPlatform');
  try {
    const d = await api(`/api/reports${p ? '?platform=' + p : ''}`);
    $('repList').innerHTML = d.items.length ? d.items.map(r => `
      <div class="report-item">
        <span class="date">${r.date}</span>
        <span class="pname2">${PLATFORM_NAMES[r.platform] || r.platform}</span>
        <span class="meta">消息 ${r.msg_count} · 重要 ${r.important_count}</span>
        <button class="btn sm" onclick="preview('${r.platform}','${r.date}')">预览</button>
        <a class="btn sm" href="/api/reports/${r.platform}/${r.date}/docx">下载</a>
      </div>`).join('') : '<div class="empty">暂无报告，可在总览页手动生成</div>';
  } catch (e) { toast(e.message, true); }
}

async function preview(platform, date) {
  try {
    await api(`/api/reports/${platform}/${date}/html`); // 鉴权校验
    $('repPreviewTitle').textContent = `${PLATFORM_NAMES[platform]} ${date} 日报`;
    $('repIframe').src = `/api/reports/${platform}/${date}/html`;
    $('repDownloadDocx').href = `/api/reports/${platform}/${date}/docx`;
    $('repPreview').style.display = 'block';
  } catch (e) { toast(e.message, true); }
}

// ── 提醒 ──
bindSeg('alertPlatform', loadAlerts);
$('alertAllRead').addEventListener('click', async () => {
  try { await api('/api/alerts/read', { method: 'POST', body: JSON.stringify({}) }); loadAlerts(); loadOverview(); toast('已全部标记'); }
  catch (e) { toast(e.message, true); }
});

async function loadAlerts() {
  const p = segValue('alertPlatform');
  try {
    const d = await api(`/api/alerts?platform=${p}&page_size=100`);
    const unread = d.items.filter(a => !a.is_read).length;
    $('alertBadge').style.display = unread ? 'inline' : 'none';
    $('alertBadge').textContent = unread;
    $('alertList').innerHTML = d.items.length ? d.items.map(a => `
      <div class="alert-item ${a.is_read ? '' : 'unread'}">
        <div class="pri p-${a.priority}">${a.priority}</div>
        <div class="body">
          <div class="src">${PLATFORM_NAMES[a.platform]} · ${esc(a.group_name) || '群'} · ${esc(a.sender) || '匿名'} · ${fmtTs(a.ts)}</div>
          <div>${esc(a.content)}</div>
          ${a.reason ? `<div style="color:var(--warn);font-size:13px;margin-top:4px">原因：${esc(a.reason)}</div>` : ''}
          ${a.suggestion ? `<div class="sugg">💡 建议：${esc(a.suggestion)}</div>` : ''}
        </div>
        ${!a.is_read ? `<button class="btn sm read-btn" onclick="markRead(${a.id})">已读</button>` : ''}
      </div>`).join('') : '<div class="empty">暂无重要提醒</div>';
  } catch (e) { toast(e.message, true); }
}

async function markRead(id) {
  try { await api('/api/alerts/read', { method: 'POST', body: JSON.stringify({ ids: [id] }) }); loadAlerts(); loadOverview(); }
  catch (e) { toast(e.message, true); }
}

// ── 设置 ──
// 保存昵称（个人中心，无需管理员）
$('saveNick').addEventListener('click', async () => {
  const nick = $('meNick').value.trim();
  try {
    const r = await api('/api/me/nickname', { method: 'POST', body: JSON.stringify({ nickname: nick }) });
    toast(`昵称已保存：${r.nickname}`);
    $('meNick').value = '';
  } catch (e) { toast(e.message, true); }
});
// 保存关键词（仅管理员）
$('saveKw').addEventListener('click', async () => {
  try {
    await api('/api/settings/keywords', { method: 'POST', body: JSON.stringify({ categories: kwData }) });
    toast('关键词已保存，各平台将自动重载');
  } catch (e) { toast(e.message, true); }
});
// 修改密码：需验证旧密码（大平台规则）
$('savePwd').addEventListener('click', async () => {
  const oldPwd = $('oldPwd').value, pwd = $('newPwd').value;
  if (pwd.length < 6) { toast('密码至少 6 位', true); return; }
  if (!oldPwd) { toast('请填写旧密码', true); return; }
  try {
    await api('/api/settings/password', { method: 'POST', body: JSON.stringify({ old_password: oldPwd, password: pwd }) });
    toast('密码已修改，请重新登录');
    $('oldPwd').value = ''; $('newPwd').value = '';
    setTimeout(() => location.href = '/login', 1200);
  } catch (e) { toast(e.message, true); }
});

async function loadSettings() {
  try {
    const s = await api('/api/settings');
    // ── 我的账号（所有用户） ──
    $('setUser').textContent = s.username;
    $('setRole').textContent = s.role === 'admin' ? '管理员' : '普通用户';
    $('meNick').placeholder = s.nickname || '给自己起个昵称';
    // ── 用户级绑定/关键词（多租户：所有用户管理自己的配置） ──
    $('aiModelName').textContent = s.ai.model || '未配置';
    $('aiInfo').innerHTML = `
      <div class="settings-row"><span class="label">模型</span><span>${s.ai.model}</span></div>
      <div class="settings-row"><span class="label">接口</span><span>${s.ai.base_url}</span></div>
      <div class="settings-row"><span class="label">API Key</span><span>${s.ai.key_set ? '已配置 ' + s.ai.key_masked : '<b style="color:var(--danger)">未配置</b>'}</span></div>
      <div class="settings-row"><span class="label">Server酱推送</span><span>${s.serverchan_set ? '已开启' : '未开启'}</span></div>
      <div class="settings-row"><span class="label">平台</span><span>${s.platforms.map(p => `${PLATFORM_NAMES[p.name]} ${p.enabled ? '启用' : '停用'} · ${p.running ? '运行中' : '已停止'}`).join('　')}</span></div>`;
    kwData = s.keywords;
    $('kwGroups').innerHTML = Object.entries(s.keywords).map(([cat, words]) => `
      <div class="kw-group">
        <label>${esc(cat)}</label>
        <div class="kw-tags">
          ${words.map(w => `<span class="kw-tag">${esc(w)}<span class="del" onclick="delKw('${esc(cat)}','${esc(w)}')">✕</span></span>`).join('')}
        </div>
        <div class="kw-add">
          <input type="text" placeholder="新增关键词" data-add="${esc(cat)}">
          <button class="btn sm" onclick="addKw('${esc(cat)}')">添加</button>
        </div>
      </div>`).join('');
    loadPlatformBinding('qq');
    loadPlatformBinding('dingtalk');
  } catch (e) { toast(e.message, true); }
}

// ── 平台账号绑定（多租户：当前用户自己的绑定） ──
async function loadPlatformBinding(platform) {
  try {
    const d = await api(`/api/settings/platforms/${platform}`);
    const c = d.config;
    const enabled = d.config.enabled !== undefined ? d.config.enabled : (c.QQ_ENABLED === 'true' || c.DINGTALK_ENABLED === 'true');
    if (platform === 'qq') {
      $('qq_app_id').value = c.QQ_APP_ID || '';
      $('qq_app_secret').value = '';
      $('qq_app_secret').placeholder = c.QQ_APP_SECRET_SET ? `已设置 ${c.QQ_APP_SECRET}（留空不变）` : '未设置';
      $('qq_env').value = c.QQ_ENV === 'sandbox' ? 'sandbox' : 'prod';
      $('qq_groups').value = c.QQ_GROUP_OPENIDS || '';
      $('qq_enabled').value = enabled ? 'true' : 'false';
    } else {
      $('dt_app_key').value = c.DINGTALK_APP_KEY || '';
      $('dt_app_secret').value = '';
      $('dt_app_secret').placeholder = c.DINGTALK_APP_SECRET_SET ? `已设置 ${c.DINGTALK_APP_SECRET}（留空不变）` : '未设置';
      $('dt_chat_ids').value = c.DINGTALK_CHAT_IDS || '';
      $('dt_enabled').value = enabled ? 'true' : 'false';
    }
  } catch (e) { toast(e.message, true); }
}

async function testBinding(platform) {
  const statusId = platform === 'qq' ? 'qq_status' : 'dt_status';
  const el = $(statusId);
  el.className = 'bind-status info'; el.textContent = '测试中…';
  // 测试连接：提交表单当前填写的值（未保存也能测），后端用这些值获取 access_token
  const body = {};
  if (platform === 'qq') {
    if ($('qq_app_id').value.trim()) body.QQ_APP_ID = $('qq_app_id').value.trim();
    if ($('qq_app_secret').value.trim()) body.QQ_APP_SECRET = $('qq_app_secret').value.trim();
    body.QQ_ENV = $('qq_env').value;
  } else {
    if ($('dt_app_key').value.trim()) body.DINGTALK_APP_KEY = $('dt_app_key').value.trim();
    if ($('dt_app_secret').value.trim()) body.DINGTALK_APP_SECRET = $('dt_app_secret').value.trim();
  }
  try {
    const d = await api(`/api/settings/platforms/${platform}/test`, { method: 'POST', body: JSON.stringify(body) });
    el.className = d.ok ? 'bind-status ok' : 'bind-status err';
    el.textContent = d.detail;
  } catch (e) { el.className = 'bind-status err'; el.textContent = e.message; }
}

async function saveBinding(platform) {
  const body = {};
  if (platform === 'qq') {
    if ($('qq_app_id').value.trim()) body.QQ_APP_ID = $('qq_app_id').value.trim();
    if ($('qq_app_secret').value.trim()) body.QQ_APP_SECRET = $('qq_app_secret').value.trim();
    body.QQ_ENV = $('qq_env').value;
    body.QQ_GROUP_OPENIDS = $('qq_groups').value.trim();
    body.QQ_ENABLED = $('qq_enabled').value;
  } else {
    if ($('dt_app_key').value.trim()) body.DINGTALK_APP_KEY = $('dt_app_key').value.trim();
    if ($('dt_app_secret').value.trim()) body.DINGTALK_APP_SECRET = $('dt_app_secret').value.trim();
    body.DINGTALK_CHAT_IDS = $('dt_chat_ids').value.trim();
    body.DINGTALK_ENABLED = $('dt_enabled').value;
  }
  const statusId = platform === 'qq' ? 'qq_status' : 'dt_status';
  const el = $(statusId);
  try {
    await api(`/api/settings/platforms/${platform}`, { method: 'POST', body: JSON.stringify(body) });
    // 下发 restart 使 worker 加载新配置
    await api(`/api/platforms/${platform}/command`, { method: 'POST', body: JSON.stringify({ cmd: 'restart' }) });
    el.className = 'bind-status ok';
    el.textContent = '✅ 配置已保存并下发重启命令（worker 将自动加载新配置）';
    loadPlatformBinding(platform);
    setTimeout(loadOverview, 3000);
  } catch (e) { el.className = 'bind-status err'; el.textContent = e.message; }
}

$('qq_test').addEventListener('click', () => testBinding('qq'));
$('qq_save').addEventListener('click', () => saveBinding('qq'));
$('dt_test').addEventListener('click', () => testBinding('dingtalk'));
$('dt_save').addEventListener('click', () => saveBinding('dingtalk'));

// ── 关键词：添加/删除立即自动保存（防抖 400ms） ──
let kwSaveTimer = null;
async function autoSaveKeywords() {
  clearTimeout(kwSaveTimer);
  kwSaveTimer = setTimeout(async () => {
    try {
      await api('/api/settings/keywords', { method: 'POST', body: JSON.stringify({ categories: kwData }) });
      toast('关键词已保存并生效');
    } catch (e) { toast('关键词保存失败: ' + e.message, true); }
  }, 400);
}
function addKw(cat) {
  const input = document.querySelector(`input[data-add="${CSS.escape(cat)}"]`);
  const w = (input.value || '').trim();
  if (!w) return;
  if (!kwData[cat]) kwData[cat] = [];
  if (!kwData[cat].includes(w)) kwData[cat].push(w);
  input.value = '';
  renderKw();
  autoSaveKeywords();
}
function delKw(cat, w) {
  kwData[cat] = (kwData[cat] || []).filter(x => x !== w);
  renderKw();
  autoSaveKeywords();
}
function renderKw() {
  $('kwGroups').innerHTML = Object.entries(kwData).map(([cat, words]) => `
    <div class="kw-group">
      <label>${esc(cat)}</label>
      <div class="kw-tags">${words.map(w => `<span class="kw-tag">${esc(w)}<span class="del" onclick="delKw('${esc(cat)}','${esc(w)}')">✕</span></span>`).join('')}</div>
      <div class="kw-add"><input type="text" placeholder="新增关键词" data-add="${esc(cat)}"><button class="btn sm" onclick="addKw('${esc(cat)}')">添加</button></div>
    </div>`).join('');
}

// ── 工具 ──
function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function fmtTs(ts) {
  if (!ts) return '';
  const d = new Date(ts > 1e12 ? ts : ts * 1000);
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

// ── 启动 ──
checkMe();
loadOverview();
loadMessages();
setInterval(() => { if ($('page-overview').classList.contains('active')) loadOverview(); }, 5000);
setInterval(() => { if ($('page-alerts').classList.contains('active')) loadAlerts(); }, 5000);
// 消息页/报告页兜底轮询（SSE 断线时仍能更新）
setInterval(() => {
  if ($('page-messages').classList.contains('active')) {
    const y = window.scrollY;
    loadMessages().then(() => window.scrollTo(0, y));
  }
  if ($('page-reports').classList.contains('active')) {
    loadReports();
  }
}, 5000);

// ── SSE 实时推送（毫秒级） ──
function initSSE() {
  const es = new EventSource('/api/stream');
  es.addEventListener('ready', () => {
    console.log('[SSE] 实时连接已建立');
  });
  es.addEventListener('message', (e) => {
    const d = JSON.parse(e.data);
    // 消息页：只刷新当前平台的列表（即时）
    if ($('page-messages').classList.contains('active') && segValue('msgPlatform') === d.platform) {
      const y = window.scrollY;
      loadMessages().then(() => window.scrollTo(0, y));
    }
    if ($('page-overview').classList.contains('active')) loadOverview();
  });
  es.addEventListener('alert', (e) => {
    const d = JSON.parse(e.data);
    const name = PLATFORM_NAMES[d.platform] || d.platform;
    toast(`⚠️ ${name} 有新重要提醒！`);
    if ($('page-alerts').classList.contains('active')) loadAlerts();
    loadOverview();   // 更新未读角标
    if ($('page-messages').classList.contains('active')) loadMessages();
  });
  es.addEventListener('report', () => {
    if ($('page-reports').classList.contains('active')) loadReports();
  });
  es.addEventListener('file', () => {
    if ($('page-files').classList.contains('active')) { loadFileCategories(); loadFiles(); }
  });
  es.onerror = () => {
    // EventSource 会自动重连；断线期间由 5s 轮询兜底
    console.log('[SSE] 连接中断，自动重连中…');
  };
}
initSSE();
