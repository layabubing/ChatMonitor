/* UI 小组件：平台切换键、事件委托、加载态 */
import { $ } from './util.js';

/** segmented control：点击切换高亮并回调当前值 */
export function bindSeg(segId, onChange) {
  const seg = $(segId);
  seg.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
    setSeg(segId, b.dataset.p);
    onChange(b.dataset.p);
  }));
}

export function segValue(segId) {
  const active = $(segId).querySelector('button.active');
  return active ? active.dataset.p : '';
}

export function setSeg(segId, value) {
  const seg = $(segId);
  let matched = false;
  seg.querySelectorAll('button').forEach((b) => {
    const on = b.dataset.p === value;
    b.classList.toggle('active', on);
    if (on) matched = true;
  });
  if (!matched) {   // 值不存在时回退到第一个
    const first = seg.querySelector('button');
    if (first) first.classList.add('active');
  }
}

/**
 * 事件委托：container 内带 data-action 的元素点击时分发到对应处理器。
 * 替代 inline onclick —— 避免字符串拼接注入，且动态内容无需重新绑定。
 *   <button data-action="read" data-id="3"> → actions.read(dataset, el, event)
 */
export function delegate(container, actions) {
  const root = typeof container === 'string' ? $(container) : container;
  root.addEventListener('click', (e) => {
    const el = e.target.closest('[data-action]');
    if (!el || !root.contains(el)) return;
    const fn = actions[el.dataset.action];
    if (fn) fn(el.dataset, el, e);
  });
}

/** 列表加载态：骨架屏 */
export function setLoading(el, rows = 3) {
  const node = typeof el === 'string' ? $(el) : el;
  node.innerHTML = '<div class="skel"></div>'.repeat(rows);
}

/** 重建 <select> 选项时保留之前选中的值（仍存在的话） */
export function refillSelect(sel, options, defaultLabel) {
  const prev = sel.value;
  sel.innerHTML = `<option value="">${defaultLabel}</option>`
    + options.map((x) => `<option></option>`).join('');
  // 用 textContent 填值，避免注入
  const opts = sel.querySelectorAll('option');
  options.forEach((x, i) => { opts[i + 1].textContent = x; opts[i + 1].value = x; });
  if (options.includes(prev)) sel.value = prev;
}
