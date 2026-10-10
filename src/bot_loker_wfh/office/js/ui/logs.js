// ---------- activity log drawer; the socket lives in systems/realtime.js ----------
import { $, closeFlyouts } from './dom.js';

const drawer = $('logDrawer');
const list = $('logList');
const toggle = $('bLogs');
const close = $('logClose');
export function toggleLogs(open = !drawer.classList.contains('show')) {
  drawer.classList.toggle('show', open);
  drawer.setAttribute('aria-hidden', String(!open));
  if (open) closeFlyouts('logDrawer');
}
toggle?.addEventListener('click', () => toggleLogs());
close?.addEventListener('click', () => toggleLogs(false));

export function addLogItem(event) {
  if (!list || !event || typeof event !== 'object') return;
  const item = document.createElement('li');
  item.textContent = `${event.employee || '-'} · ${event.task || '-'} · ${event.status || ''}${event.error_code ? ` · ${event.error_code}` : ''}`;
  list.append(item);
  while (list.children.length > 100) list.firstChild.remove();
}