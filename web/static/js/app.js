/* 主控：登录态、导航调度、SSE 状态机（在线停轮询 / 断线才兜底）
 *
 * 导航：tab 点击 → navigate(page) → 对应模块 load()（按需加载，不再全量预载）
 * 实时：SSE 在线时页面更新全靠事件推送；断线时才开启 10s 兜底轮询当前页。
 */
import { $, api, toast, PLATFORM_NAMES } from './util.js';
import * as overview from './pages/overview.js';
import * as messages from './pages/messages.js';
import * as alerts from './pages/alerts.js';
import * as reports from './pages/reports.js';
import * as files from './pages/files.js';
import * as settings from './pages/settings.js';

const pages = { overview, messages, alerts, reports, files, settings };
let currentPage = 'overview';
let booted = false;

function navigate(page) {
  if (!pages[page]) page = 'overview';
  currentPage = page;
  localStorage.setItem('cm_tab', page);
  document.querySelectorAll('#mainNav .nav-item').forEach((t) => t.classList.toggle('active', t.dataset.page === page));
  document.querySelectorAll('.page').forEach((p) => p.classList.toggle('active', p.id === 'page-' + page));
  pages[page].load();
}

// ── SSE 状态机 + 兜底轮询 ──
let pollTimer = null;

function startFallback() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    // 断线期间轻量刷新当前页（消息页保持滚动位置）
    if (currentPage === 'messages') {
      const y = window.scrollY;
      messages.load().then(() => window.scrollTo(0, y));
    } else {
      pages[currentPage].load();
    }
    alerts.updateBadge();
  }, 10000);
}

function stopFallback() {
  clearInterval(pollTimer);
  pollTimer = null;
}

function setSseDot(online) {
  const dot = $('sseDot');
  dot.className = 'sse-dot ' + (online ? 'online' : 'offline');
  dot.title = online ? '实时推送已连接' : '实时推送重连中（10s 轮询兜底）';
  $('sseText').textContent = online ? '实时已连接' : '重连中…';
}

function initSSE() {
  const es = new EventSource('/api/stream');
  es.onopen = () => { setSseDot(true); stopFallback(); };
  es.onerror = () => { setSseDot(false); startFallback(); };   // EventSource 自动重连
  es.addEventListener('message', (e) => {
    const d = JSON.parse(e.data);
    messages.onNewMessage(d.platform, currentPage === 'messages');
    if (currentPage === 'overview') overview.load();
  });
  es.addEventListener('alert', (e) => {
    const d = JSON.parse(e.data);
    alerts.updateBadge();
    if (currentPage !== 'alerts') toast(`⚠️ ${PLATFORM_NAMES[d.platform] || d.platform} 有新的重要提醒`);
    else alerts.load();
    if (currentPage === 'overview') overview.load();
  });
  es.addEventListener('report', () => {
    if (currentPage === 'reports') reports.load();
    else toast('📄 新的日报已生成，可在「报告」页查看');
    if (currentPage === 'overview') overview.load();
  });
  es.addEventListener('file', () => { if (currentPage === 'files') files.load(); });
}

// ── 启动 ──
async function boot() {
  let me;
  try {
    me = await api('/api/me');
  } catch { location.href = '/login'; return; }
  const displayName = me.nickname || me.username;
  $('who').textContent = displayName;
  $('who').title = me.role === 'admin' ? '管理员' : '普通用户';
  $('whoAvatar').textContent = (displayName[0] || '?').toUpperCase();

  if (!booted) {
    booted = true;
    const ctx = { navigate, setMsgPlatform: messages.setPlatform };
    Object.values(pages).forEach((p) => p.init && p.init(ctx));
    document.querySelectorAll('#mainNav .nav-item').forEach((t) =>
      t.addEventListener('click', () => navigate(t.dataset.page)));
    $('logout').addEventListener('click', async () => {
      await api('/api/logout', { method: 'POST' });
      location.href = '/login';
    });
  }

  navigate(localStorage.getItem('cm_tab') || 'overview');
  alerts.updateBadge();
  initSSE();
}

boot();
