// ---------- simple freelance project board: list + click for detail ----------
import { store } from '../core/store.js';
import { $, el, ago, get, post, toast, OFFLINE } from './dom.js';
import { loadPrefs, savePrefNow } from '../systems/prefs.js';

const SOURCES = [['', '✨ Semua'], ['freelancer', '🌍 Freelancer'], ['projects.co.id', '🏠 Projects.co.id'], ['telegram', '🏠 Telegram']];
const VIEWS = [['all', '📋 Aktif'], ['new', '🆕 Baru'], ['old', '🕰️ Lama']];
let boardOpen = false, source = '', view = 'all', current = null;

export function toggleBoard(v = !boardOpen) {
  boardOpen = v; $('board').classList.toggle('show', v);
  if (v) { render(); loadProfile(); }
}
$('bBoard').onclick = () => toggleBoard();
$('boardClose').onclick = () => toggleBoard(false);
$('board').onclick = e => { if (e.target === $('board')) toggleBoard(false); };

function chips(id, items, active, pick) {
  const box = $(id);
  if (!box) return;
  box.replaceChildren(...items.map(([key, label]) => {
    const b = el('button', 'chipb' + (key === active ? ' on' : ''), label);
    b.onclick = () => pick(key);
    return b;
  }));
}

async function render() {
  chips('boardSources', SOURCES, source, key => { source = key; current = null; render(); });
  chips('boardViews', VIEWS, view, key => { view = key; current = null; render(); });
  const list = $('boardList');
  if (current) return detail(current);
  if (!store.live) { list.replaceChildren(el('div', 'empty', OFFLINE)); return; }
  list.replaceChildren(el('div', 'empty', '⏳ Memuat…'));
  let data;
  try {
    const url = `leads.json?view=${view}` + (source ? `&source=${encodeURIComponent(source)}` : '');
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw 0;
    data = await r.json();
  } catch { list.replaceChildren(el('div', 'empty', 'Gagal memuat, coba lagi')); return; }
  if (!data.items.length) { list.replaceChildren(el('div', 'empty', 'Belum ada proyek')); return; }
  list.replaceChildren(...data.items.map(lead));
}

function lead(l) {
  const card = el('div', 'job');
  const top = el('div', 'jtop');
  const sourceClass = (l.source || '').toLowerCase().includes('freelancer') ? 'freelancer'
    : (l.source || '').toLowerCase().includes('projects') ? 'projects' : 'telegram';
  const sourceLabel = sourceClass === 'freelancer' ? '🌍 Freelancer'
    : sourceClass === 'projects' ? '🏠 Projects.co.id' : '✈️ Telegram';

  top.append(el('span', `tag tag-src ${sourceClass}`, sourceLabel));
  if (l.budget) top.append(el('span', 'b-badge', l.budget));

  const title = el('div', 'jt', l.title);
  const meta = el('div', 'meta', [el('span', null, '🕒 ' + (ago(l.posted_at || l.fetched_at) || '—'))]);
  if (l.status && l.status !== 'NEW') {
    const stClass = l.status === 'APPLIED' ? 'good' : l.status === 'PASS' ? 'low' : 'mid';
    meta.append(el('span', `tag ${stClass}`, l.status));
  } else {
    meta.append(el('span', 'tag good', '🆕 Baru'));
  }

  card.append(top, title, meta);
  card.onclick = () => { current = l; detail(l); };
  return card;
}

function row(label, value) {
  const p = el('div', 'period');
  p.append(el('b', null, label), el('div', null, value || '—'));
  return p;
}

function detail(l) {
  const list = $('boardList');
  const wrap = el('div', 'prof');
  const back = el('button', 'btn', '← Kembali');
  back.onclick = () => { current = null; render(); };
  wrap.append(back, el('h4', null, l.title));

  const grid = el('div', 'periods');
  grid.append(
    row('Sumber', l.source),
    row('Jenis', l.kind),
    row('Budget', l.budget),
    row('Status', l.status),
    row('Diposting', ago(l.posted_at || l.fetched_at)),
    row('Diambil', ago(l.fetched_at)),
  );
  wrap.append(grid);

  if (l.description) {
    wrap.append(el('h4', null, 'Deskripsi'), el('p', 'note', l.description));
  }
  if (l.proposal) {
    wrap.append(el('h4', null, 'Proposal terakhir'), el('p', 'note', l.proposal));
  }
  const open = document.createElement('a');
  open.className = 'btn ok'; open.href = l.url; open.target = '_blank'; open.rel = 'noopener noreferrer';
  open.textContent = '🌐 Buka proyek';
  wrap.append(open);
  list.replaceChildren(wrap);
}
