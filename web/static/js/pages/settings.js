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
    if (btn.dataset.sub === 'update') loadUpdate();   // admin 子页：进入时拉取缓存状态（不走网络）
  });
  const savedSub = localStorage.getItem('cm_settings_sub');
  if (savedSub) {
    const btn = document.querySelector(`#settingsNav button[data-sub="${savedSub}"]`);
    if (btn) btn.click();
  }

  // 账号
  $('saveNick').addEventListener('click', saveNickname);
  $('savePwd').addEventListener('click', savePassword);

  // 系统更新（仅 admin 可见可用，按钮本身始终存在）
  $('updCheck').addEventListener('click', checkUpdate);
  $('updApply').addEventListener('click', applyUpdate);

  // 绑定
  ['qq', 'dingtalk', 'feishu', 'workwechat'].forEach((p) => {
    const f = FIELD_MAP[p];
    $(`${f.testId}_test`).addEventListener('click', () => testBinding(p));
    $(`${f.testId}_save`).addEventListener('click', () => saveBinding(p));
  });

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
    if (s.role === 'admin') $('settingsNavUpdate').hidden = false;   // 系统更新仅 admin 可见
    $('meNick').placeholder = s.nickname || '给自己起个昵称';
    renderAiInfo(s);
    kwData = s.keywords || {};
    renderKeywords();
    await Promise.all(Object.keys(FIELD_MAP).map(loadBinding));
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

// ── 平台绑定（注册表驱动：新增平台 = 这里加一行 + index.html 加表单） ──
const FIELD_MAP = {
  qq: {
    testId: 'qq', id: 'qq_app_id', id_key: 'QQ_APP_ID',
    secret: 'qq_app_secret', secret_key: 'QQ_APP_SECRET',
    env: 'qq_env', env_key: 'QQ_ENV',
    groups: 'qq_groups', groups_key: 'QQ_GROUP_OPENIDS',
    enabled: 'qq_enabled', enabled_key: 'QQ_ENABLED', status: 'qq_status',
  },
  dingtalk: {
    testId: 'dt', id: 'dt_app_key', id_key: 'DINGTALK_APP_KEY',
    secret: 'dt_app_secret', secret_key: 'DINGTALK_APP_SECRET',
    groups: 'dt_chat_ids', groups_key: 'DINGTALK_CHAT_IDS',
    enabled: 'dt_enabled', enabled_key: 'DINGTALK_ENABLED', status: 'dt_status',
  },
  feishu: {
    testId: 'fs', id: 'fs_app_id', id_key: 'FEISHU_APP_ID',
    secret: 'fs_app_secret', secret_key: 'FEISHU_APP_SECRET',
    groups: 'fs_chat_ids', groups_key: 'FEISHU_CHAT_IDS',
    enabled: 'fs_enabled', enabled_key: 'FEISHU_ENABLED', status: 'fs_status',
  },
  workwechat: {
    testId: 'ww', id: 'ww_corp_id', id_key: 'WORKWECHAT_CORP_ID',
    secret: 'ww_secret', secret_key: 'WORKWECHAT_SECRET',
    groups: 'ww_chat_ids', groups_key: 'WORKWECHAT_CHAT_IDS',
    enabled: 'ww_enabled', enabled_key: 'WORKWECHAT_ENABLED', status: 'ww_status',
    extra: [
      { id: 'ww_agent_id', key: 'WORKWECHAT_AGENT_ID' },
      { id: 'ww_token', key: 'WORKWECHAT_TOKEN', secret: true },
      { id: 'ww_aes_key', key: 'WORKWECHAT_AES_KEY', secret: true },
    ],
  },
};

async function loadBinding(platform) {
  const F = FIELD_MAP[platform];
  try {
    const d = await api(`/api/settings/platforms/${platform}`);
    const c = d.config;
    const enabled = c.enabled !== undefined ? c.enabled : (c[F.enabled_key] === 'true');
    if (F.env) $(F.env).value = (c[F.env_key] === 'sandbox' ? 'sandbox' : 'prod');
    $(F.id).value = c[F.id_key] || '';
    $(F.secret).placeholder = c[F.secret_key + '_SET'] ? `已设置 ${c[F.secret_key]}（留空不变）` : '未设置';
    if (F.groups) $(F.groups).value = c[F.groups_key] || '';
    for (const ex of (F.extra || [])) {
      const el = $(ex.id);
      if (!el) continue;
      if (ex.secret) {
        el.placeholder = c[ex.key + '_SET'] ? `已设置 ${c[ex.key]}（留空不变）` : '未设置';
        el.value = '';
      } else {
        el.value = c[ex.key] || '';
      }
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
  if (idVal) body[F.id_key] = idVal;
  if (secretVal) body[F.secret_key] = secretVal;
  if (F.env && $(F.env)) body[F.env_key] = $(F.env).value;
  if (F.groups && $(F.groups)) body[F.groups_key] = $(F.groups).value.trim();
  if (F.enabled && $(F.enabled)) body[F.enabled_key] = $(F.enabled).value;
  for (const ex of (F.extra || [])) {
    const el = $(ex.id);
    if (el && el.value.trim()) body[ex.key] = el.value.trim();
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

// ── 系统更新（仅 admin；每一次 commit 即一个版本） ──
async function loadUpdate() {
  try {
    renderUpdate(await api('/api/update/status'));
  } catch (e) { $('updStatus').className = 'bind-status err'; $('updStatus').textContent = e.message; }
}

function renderUpdate(d) {
  const cur = d.current || {};
  $('updCurrent').textContent = cur.hash ? `${cur.hash} · ${cur.message}（${cur.time}）` : '未知（非 git 部署）';
  $('updRepo').textContent = d.repo || '未配置';
  $('updCheckedAt').textContent = d.checked_at ? new Date(d.checked_at * 1000).toLocaleString() : '尚未检查';
  const state = $('updState');
  if (d.update_available) {
    state.innerHTML = `<b style="color:var(--danger)">发现 ${d.behind} 个新提交，可更新</b>`;
  } else if (d.error) {
    state.textContent = '检查失败';
  } else {
    state.textContent = d.checked_at ? '已是最新版本 ✓' : '尚未检查，点击「检查更新」获取远端状态';
  }
  $('updApply').disabled = !d.update_available || d.busy;
  $('updCommits').innerHTML = (d.commits || []).map((c) => `
    <div class="settings-row"><span class="label"><code>${esc(c.hash)}</code></span>
      <span>${esc(c.message)} <span class="hint-inline">${esc(c.author)} · ${esc(c.time)}</span></span></div>`).join('');
  const st = $('updStatus');
  if (d.error) { st.className = 'bind-status err'; st.textContent = d.error; }
}

async function checkUpdate() {
  const st = $('updStatus');
  st.className = 'bind-status info';
  st.textContent = '正在连接 GitHub 检查更新…';
  $('updCheck').disabled = true;
  try {
    const d = await api('/api/update/check', { method: 'POST', body: '{}' });
    renderUpdate(d);
    if (!d.error) {
      st.className = 'bind-status ' + (d.update_available ? 'info' : 'ok');
      st.textContent = d.update_available ? `发现 ${d.behind} 个新提交，请确认后更新` : '已是最新版本 ✓';
    }
  } catch (e) { st.className = 'bind-status err'; st.textContent = e.message; }
  finally { $('updCheck').disabled = false; }
}

async function applyUpdate() {
  if (!confirm('确认更新服务端到 GitHub 最新版本？\n\n更新采用 fast-forward，只更新代码，不会影响本地数据（消息库、配置、报告等）。\n更新完成后服务将重启以生效。')) return;
  const st = $('updStatus');
  st.className = 'bind-status info';
  st.textContent = '正在更新，请勿关闭页面…';
  $('updApply').disabled = true;
  try {
    const d = await api('/api/update/apply', { method: 'POST', body: '{}' });
    if (d.warning) { st.className = 'bind-status err'; st.textContent = d.warning; return; }
    st.className = 'bind-status ok';
    if (d.restart === 'auto') {
      st.textContent = `✅ ${d.message}，服务正在自动重启，约 10 秒后刷新页面…`;
      setTimeout(() => location.reload(), 10000);
    } else {
      st.textContent = `✅ ${d.message}。请重启服务使新版本生效。`;
    }
    loadUpdate();
  } catch (e) {
    st.className = 'bind-status err';
    st.textContent = e.message;
    $('updApply').disabled = false;
  }
}
