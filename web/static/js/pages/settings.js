/* 设置页：子导航分组 —— 账号 / 平台绑定 / 关键词库 / AI 与状态
 * 交互约定：
 * - 关键词：添加/删除后 400ms 防抖自动保存（无手动保存按钮）
 * - 绑定保存：worker 每 15s 自动扫描热加载，无需也不下发 restart（避免误杀本地进程）
 */
import { $, api, esc, toast, debounce, PLATFORM_NAMES } from '../util.js';
import { delegate } from '../ui.js';

let kwData = {};
let loaded = false;

export function init() {
  // 子导航
  $('settingsNav').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-sub]');
    if (!btn) return;
    document.querySelectorAll('#settingsNav button').forEach((b) => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.subpage').forEach((p) => p.classList.toggle('active', p.id === 'sub-' + btn.dataset.sub));
    localStorage.setItem('cm_settings_sub', btn.dataset.sub);
  });
  const savedSub = localStorage.getItem('cm_settings_sub');
  if (savedSub) {
    const btn = document.querySelector(`#settingsNav button[data-sub="${savedSub}"]`);
    if (btn) btn.click();
  }

  // 账号
  $('saveNick').addEventListener('click', saveNickname);
  $('savePwd').addEventListener('click', savePassword);

  // 绑定
  $('qq_test').addEventListener('click', () => testBinding('qq'));
  $('qq_save').addEventListener('click', () => saveBinding('qq'));
  $('dt_test').addEventListener('click', () => testBinding('dingtalk'));
  $('dt_save').addEventListener('click', () => saveBinding('dingtalk'));

  // 关键词：事件委托（del/add/del-cat），无 inline onclick
  $('kwAddCat').addEventListener('click', addCategory);
  $('kwNewCat').addEventListener('keydown', (e) => { if (e.key === 'Enter') addCategory(); });
  delegate('kwGroups', {
    'del-word': (ds) => { delWord(ds.cat, ds.word); },
    'add-word': (ds, el) => {
      const input = el.closest('.kw-add').querySelector('input');
      addWord(ds.cat, input);
    },
    'del-cat': (ds) => { delCategory(ds.cat); },
  });
  // 输入框回车 = 添加该分类关键词
  $('kwGroups').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.matches('.kw-add input')) {
      addWord(e.target.dataset.cat, e.target);
    }
  });
}

export async function load() {
  if (loaded) return;   // 每次进设置页不重复拉全部；子操作自行局部刷新
  try {
    const s = await api('/api/settings');
    loaded = true;      // 成功后才置位，失败时下次进入可重试
    $('setUser').textContent = s.username;
    $('setRole').textContent = s.role === 'admin' ? '管理员' : '普通用户';
    $('meNick').placeholder = s.nickname || '给自己起个昵称';
    renderAiInfo(s);
    kwData = s.keywords || {};
    renderKeywords();
    await Promise.all([loadBinding('qq'), loadBinding('dingtalk')]);
  } catch (e) { toast(e.message, true); }
}

// ── 账号 ──
async function saveNickname() {
  const nick = $('meNick').value.trim();
  try {
    const r = await api('/api/me/nickname', { method: 'POST', body: JSON.stringify({ nickname: nick }) });
    toast(`昵称已保存：${r.nickname}`);
    $('meNick').value = '';
    $('meNick').placeholder = r.nickname;
  } catch (e) { toast(e.message, true); }
}

async function savePassword() {
  const oldPwd = $('oldPwd').value;
  const pwd = $('newPwd').value;
  if (!oldPwd) { toast('请填写旧密码', true); return; }
  if (pwd.length < 6) { toast('密码至少 6 位', true); return; }
  try {
    await api('/api/settings/password', { method: 'POST', body: JSON.stringify({ old_password: oldPwd, password: pwd }) });
    toast('密码已修改，请重新登录');
    setTimeout(() => { location.href = '/login'; }, 1200);
  } catch (e) { toast(e.message, true); }
}

// ── 平台绑定 ──
const FIELD_MAP = {
  qq: { id: 'qq_app_id', secret: 'qq_app_secret', env: 'qq_env', groups: 'qq_groups', enabled: 'qq_enabled', status: 'qq_status' },
  dingtalk: { id: 'dt_app_key', secret: 'dt_app_secret', groups: 'dt_chat_ids', enabled: 'dt_enabled', status: 'dt_status' },
};

async function loadBinding(platform) {
  const F = FIELD_MAP[platform];
  try {
    const d = await api(`/api/settings/platforms/${platform}`);
    const c = d.config;
    const enabled = c.enabled !== undefined ? c.enabled : (c.QQ_ENABLED === 'true' || c.DINGTALK_ENABLED === 'true');
    if (platform === 'qq') {
      $(F.id).value = c.QQ_APP_ID || '';
      $(F.secret).placeholder = c.QQ_APP_SECRET_SET ? `已设置 ${c.QQ_APP_SECRET}（留空不变）` : '未设置';
      $(F.env).value = c.QQ_ENV === 'sandbox' ? 'sandbox' : 'prod';
      $(F.groups).value = c.QQ_GROUP_OPENIDS || '';
    } else {
      $(F.id).value = c.DINGTALK_APP_KEY || '';
      $(F.secret).placeholder = c.DINGTALK_APP_SECRET_SET ? `已设置 ${c.DINGTALK_APP_SECRET}（留空不变）` : '未设置';
      $(F.groups).value = c.DINGTALK_CHAT_IDS || '';
    }
    $(F.secret).value = '';
    $(F.enabled).value = enabled ? 'true' : 'false';
  } catch (e) { toast(e.message, true); }
}

function collectBinding(platform) {
  const F = FIELD_MAP[platform];
  const body = {};
  const idVal = $(F.id).value.trim();
  const secretVal = $(F.secret).value.trim();
  if (platform === 'qq') {
    if (idVal) body.QQ_APP_ID = idVal;
    if (secretVal) body.QQ_APP_SECRET = secretVal;
    if ($(F.env)) body.QQ_ENV = $(F.env).value;
    if ($(F.groups)) body.QQ_GROUP_OPENIDS = $(F.groups).value.trim();
    if ($(F.enabled)) body.QQ_ENABLED = $(F.enabled).value;
  } else {
    if (idVal) body.DINGTALK_APP_KEY = idVal;
    if (secretVal) body.DINGTALK_APP_SECRET = secretVal;
    if ($(F.groups)) body.DINGTALK_CHAT_IDS = $(F.groups).value.trim();
    if ($(F.enabled)) body.DINGTALK_ENABLED = $(F.enabled).value;
  }
  return body;
}

async function testBinding(platform) {
  const el = $(FIELD_MAP[platform].status);
  el.className = 'bind-status info';
  el.textContent = '测试中…';
  try {
    const d = await api(`/api/settings/platforms/${platform}/test`, {
      method: 'POST', body: JSON.stringify(collectBinding(platform)),
    });
    el.className = d.ok ? 'bind-status ok' : 'bind-status err';
    el.textContent = d.detail;
  } catch (e) { el.className = 'bind-status err'; el.textContent = e.message; }
}

async function saveBinding(platform) {
  const el = $(FIELD_MAP[platform].status);
  try {
    await api(`/api/settings/platforms/${platform}`, {
      method: 'POST', body: JSON.stringify(collectBinding(platform)),
    });
    // worker 每 15s 自动扫描绑定并热加载，无需重启进程
    el.className = 'bind-status ok';
    el.textContent = '✅ 已保存，worker 将在约 15 秒内自动应用（无需重启）';
    loadBinding(platform);
  } catch (e) { el.className = 'bind-status err'; el.textContent = e.message; }
}

// ── 关键词库（自动保存） ──
function renderKeywords() {
  $('kwGroups').innerHTML = Object.entries(kwData).map(([cat, words]) => `
    <div class="kw-group">
      <label>${esc(cat)}<span class="kw-cat-del" data-action="del-cat" data-cat="${esc(cat)}" title="删除该分类">✕</span></label>
      <div class="kw-tags">
        ${words.map((w) => `<span class="kw-tag">${esc(w)}<span class="del" data-action="del-word" data-cat="${esc(cat)}" data-word="${esc(w)}">✕</span></span>`).join('')}
      </div>
      <div class="kw-add">
        <input type="text" placeholder="新增关键词" data-cat="${esc(cat)}">
        <button class="btn sm" data-action="add-word" data-cat="${esc(cat)}">添加</button>
      </div>
    </div>`).join('') || '<div class="empty">还没有关键词分类，先在上方新增一个分类</div>';
}

const autoSave = debounce(async () => {
  const hint = $('kwSaveHint');
  try {
    await api('/api/settings/keywords', { method: 'POST', body: JSON.stringify({ categories: kwData }) });
    hint.textContent = '已自动保存并生效 ✓';
    hint.classList.add('flash');
    setTimeout(() => { hint.textContent = '修改后自动保存 ✓'; hint.classList.remove('flash'); }, 2000);
  } catch (e) {
    hint.textContent = '保存失败：' + e.message;
    toast('关键词保存失败: ' + e.message, true);
  }
}, 400);

function addWord(cat, input) {
  const w = (input.value || '').trim();
  if (!w) return;
  if (!kwData[cat]) kwData[cat] = [];
  if (!kwData[cat].includes(w)) kwData[cat].push(w);
  input.value = '';
  renderKeywords();
  autoSave();
}

function delWord(cat, w) {
  kwData[cat] = (kwData[cat] || []).filter((x) => x !== w);
  renderKeywords();
  autoSave();
}

function addCategory() {
  const name = $('kwNewCat').value.trim();
  if (!name) return;
  if (kwData[name]) { toast('分类已存在', true); return; }
  kwData[name] = [];
  $('kwNewCat').value = '';
  renderKeywords();
  autoSave();
}

function delCategory(cat) {
  if (!confirm(`删除分类「${cat}」及其 ${kwData[cat]?.length || 0} 个关键词？`)) return;
  delete kwData[cat];
  renderKeywords();
  autoSave();
}

// ── AI 与状态 ──
function renderAiInfo(s) {
  $('aiModelName').textContent = s.ai.model || '未配置';
  $('aiInfo').innerHTML = `
    <div class="settings-row"><span class="label">模型</span><span>${esc(s.ai.model || '未配置')}</span></div>
    <div class="settings-row"><span class="label">接口</span><span>${esc(s.ai.base_url || '未配置')}</span></div>
    <div class="settings-row"><span class="label">API Key</span><span>${s.ai.key_set ? '已配置 ' + esc(s.ai.key_masked) : '<b style="color:var(--danger)">未配置</b>'}</span></div>
    <div class="settings-row"><span class="label">Server酱推送</span><span>${s.serverchan_set ? '已开启' : '未开启'}</span></div>
    <div class="settings-row"><span class="label">平台</span><span>${s.platforms.map((p) => `${PLATFORM_NAMES[p.name]} ${p.enabled ? '启用' : '停用'} · ${p.running ? '运行中' : '已停止'}`).join('　')}</span></div>`;
}
