/* 基础工具：DOM 选择、API 封装、格式化、toast */

export const $ = (id) => document.getElementById(id);
export const PLATFORM_NAMES = { qq: 'QQ', dingtalk: '钉钉' };

/** HTML 转义（防 XSS），一律用于插入 innerHTML 的用户/消息文本 */
export function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** 友好时间：今天只显示 HH:mm，昨天加前缀，更早显示完整日期 */
export function fmtTs(ts) {
  if (!ts) return '';
  const d = new Date(ts > 1e12 ? ts : ts * 1000);
  const now = new Date();
  const p = (n) => String(n).padStart(2, '0');
  const hm = `${p(d.getHours())}:${p(d.getMinutes())}`;
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return hm;
  const yesterday = new Date(now); yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return `昨天 ${hm}`;
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${hm}`;
}

export function fmtSize(n) {
  if (!n) return '0B';
  if (n < 1024) return n + 'B';
  if (n < 1048576) return (n / 1024).toFixed(1) + 'KB';
  return (n / 1048576).toFixed(1) + 'MB';
}

/** 堆叠式 toast：多条消息并存，各自 2.6s 后淡出 */
export function toast(msg, isErr = false) {
  const box = $('toasts');
  const item = document.createElement('div');
  item.className = 'toast-item' + (isErr ? ' err' : '');
  item.textContent = msg;
  box.appendChild(item);
  setTimeout(() => {
    item.classList.add('leaving');
    setTimeout(() => item.remove(), 260);
  }, 2600);
}

/** 统一 API 封装：401 跳登录、403/其他错误抛带后端 error 的 Error */
export async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (r.status === 401) { location.href = '/login'; throw new Error('未登录'); }
  if (r.status === 403) { throw new Error('没有权限执行此操作'); }
  if (!r.ok) {
    let msg = '请求失败';
    try { msg = (await r.json()).error || msg; } catch { /* 非 JSON 响应 */ }
    throw new Error(msg);
  }
  return r.json();
}

/** 简单防抖 */
export function debounce(fn, ms = 400) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
