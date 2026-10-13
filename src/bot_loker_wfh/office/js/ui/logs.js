// ---------- live employee monitor: stored meeting, learning, and report data ----------
import { $, closeFlyouts } from './dom.js';
import { get } from '../infrastructure/office-api.js';
import { staff, staffMood } from '../characters/team.js';
import { MOODS } from '../characters/body.js';

const drawer = $('logDrawer');
const toggle = $('bLogs');
const close = $('logClose');
const period = $('observerPeriod');
const state = $('observerState');
const updated = $('observerUpdated');

function when(value) {
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value || '');
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('id-ID', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

function nameFor(id) {
  return staff.find(character => character.def.id === id)?.name || id || 'Karyawan';
}

function emptyList(list, message) {
  const item = document.createElement('li');
  item.className = 'observer-empty';
  item.textContent = message;
  list.replaceChildren(item);
}

function renderConversations(items) {
  const list = $('observerConversations');
  if (!items.length) {
    emptyList(list, 'Belum ada tanya-jawab web atau transkrip rapat tersimpan pada periode ini.');
    return;
  }
  list.replaceChildren(...items.map(event => {
    const item = document.createElement('li');
    item.className = 'observer-entry';
    const head = document.createElement('div');
    head.className = 'observer-entry-head';
    const who = document.createElement('strong');
    who.textContent = event.speaker === 'owner' ? 'Owner' : nameFor(event.employee_id);
    const time = document.createElement('time');
    time.dateTime = event.created_at || '';
    time.textContent = when(event.created_at);
    head.append(who, time);
    const body = document.createElement('p');
    body.textContent = event.content || '';
    const context = document.createElement('small');
    context.textContent = `${event.title || 'Rapat'} · ${event.event_type || event.channel || 'catatan'}`;
    item.append(head, context, body);
    return item;
  }));
}

function renderMemories(items) {
  const list = $('observerMemories');
  if (!items.length) {
    emptyList(list, 'Belum ada memori pembelajaran tersimpan pada periode ini.');
    return;
  }
  list.replaceChildren(...items.map(memory => {
    const item = document.createElement('li');
    item.className = 'observer-entry';
    const head = document.createElement('div');
    head.className = 'observer-entry-head';
    const who = document.createElement('strong');
    who.textContent = nameFor(memory.employee_id);
    const time = document.createElement('time');
    time.dateTime = memory.created_at || '';
    time.textContent = when(memory.created_at);
    head.append(who, time);
    const body = document.createElement('p');
    body.textContent = memory.content || '';
    const kind = document.createElement('small');
    const importance = Number(memory.importance);
    kind.textContent = `${memory.kind || 'memori'} · kepentingan ${Number.isFinite(importance) ? `${Math.round(importance * 100)}%` : '—'}`;
    item.append(head, kind, body);
    return item;
  }));
}

function renderTeam(performanceRows) {
  const moods = $('observerMood');
  moods.replaceChildren(...staff.map(character => {
    const item = document.createElement('div');
    item.className = 'observer-mood';
    const who = document.createElement('strong');
    who.textContent = character.name;
    const mood = staffMood(character, performance.now() / 1000);
    const signal = document.createElement('span');
    signal.textContent = `${MOODS[mood]?.label || mood} · energi ${Math.round(character.energy ?? 0)}%`;
    item.append(who, signal);
    return item;
  }));

  const list = $('observerPerformance');
  if (!performanceRows.length) {
    emptyList(list, 'Belum ada laporan kinerja pada periode ini.');
    return;
  }
  const labels = new Map(staff.map(character => [character.def.id, character.name]));
  list.replaceChildren(...performanceRows
    .slice()
    .sort((a, b) => b.avg_score - a.avg_score)
    .map(report => {
      const item = document.createElement('li');
      item.className = 'observer-entry';
      const head = document.createElement('div');
      head.className = 'observer-entry-head';
      const who = document.createElement('strong');
      who.textContent = labels.get(report.employee) || report.employee;
      const score = document.createElement('span');
      score.textContent = `Skor ${Number(report.avg_score).toFixed(2)}`;
      head.append(who, score);
      const detail = document.createElement('small');
      const rating = report.avg_rating == null ? 'belum ada rating owner' : `rating owner ${Number(report.avg_rating).toFixed(2)}/5`;
      detail.textContent = `${report.reports} laporan · ${rating}`;
      item.append(head, detail);
      return item;
    }));
}

async function refreshMonitor() {
  if (!state) return;
  state.textContent = 'Mengambil data karyawan…';
  const result = await get(`/observability.json?hours=${encodeURIComponent(period.value || '24')}`);
  if (!result.ok) {
    state.textContent = 'Data pemantauan tidak tersedia';
    updated.textContent = result.status === 0
      ? 'Server kantor tidak terjangkau. Jalankan web kantor dan pastikan SUPABASE_DB_URL tersedia.'
      : `Database belum dapat dibaca (HTTP ${result.status}). Periksa koneksi Supabase dan skema loker.`;
    return;
  }
  const data = result.data || {};
  renderConversations(data.conversations || []);
  renderMemories(data.memories || []);
  renderTeam(data.performance || []);
  state.textContent = 'Terhubung ke data kantor';
  const hours = Number(data.hours);
  const scope = hours === 0 ? 'semua data' : `${hours} jam terakhir`;
  updated.textContent = `Diperbarui ${when(data.generated_at)} · ${scope}` +
    (data.truncated ? ' · sebagian hasil dibatasi 1.000 baris' : '');
}

export function toggleLogs(open = !drawer.classList.contains('show')) {
  drawer.classList.toggle('show', open);
  drawer.setAttribute('aria-hidden', String(!open));
  if (open) {
    closeFlyouts('logDrawer');
    refreshMonitor();
  }
}

toggle?.addEventListener('click', () => toggleLogs());
close?.addEventListener('click', () => toggleLogs(false));
$('observerRefresh')?.addEventListener('click', refreshMonitor);
period?.addEventListener('change', refreshMonitor);

document.querySelectorAll('[data-observer-tab]').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('[data-observer-tab]').forEach(button => {
      const selected = button === tab;
      button.setAttribute('aria-selected', String(selected));
      $(button.getAttribute('aria-controls')).hidden = !selected;
    });
  });
  tab.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const tabs = [...document.querySelectorAll('[data-observer-tab]')];
    const next = tabs[(tabs.indexOf(tab) + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    next.focus();
    next.click();
  });
});

setInterval(() => {
  if (drawer.classList.contains('show') && document.visibilityState === 'visible') refreshMonitor();
}, 60000);

export function openMonitor() { toggleLogs(true); }

export function addLogItem(event) {
  const list = $('logList');
  if (!list || !event || typeof event !== 'object') return;
  if (list.querySelector('.observer-empty')) list.replaceChildren();
  const item = document.createElement('li');
  const at = when(event.timestamp);
  item.textContent = `${at ? `${at} · ` : ''}${event.employee || '-'} · ${event.task || '-'} · ${event.status || ''}${event.error_code ? ` · ${event.error_code}` : ''}`;
  list.prepend(item);
  while (list.children.length > 100) list.lastElementChild.remove();
}
