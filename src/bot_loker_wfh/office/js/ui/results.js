// ---------- results: what each employee actually produced ----------
import { store } from '../core/store.js';
import { clamp } from '../core/util.js';
import { MOODS } from '../characters/body.js';
import { staff } from '../characters/team.js';
import { $, el, ago, starsHtml, faceStyle, OFFLINE } from './dom.js';
import { chatWith } from './card.js';

const RESULT_VIEW = { tegar: 'tracking', sari: 'screened', eli: 'screened', cora: 'drafts', bimo: 'bid', lulu: 'drafts', faris: 'applied', subi: 'applied', tara: 'tracking', ivan: 'tracking' };
const viewFor = c => c.def.hunt ? `view=${c.def.hunt.what === 'lowongan' ? 'jobs' : 'leads'}&source=${encodeURIComponent(c.def.hunt.src)}` : `view=${RESULT_VIEW[c.def.id]}`;
export const TAG = {
  CANDIDATE: ['✅', 'Cocok', 'good'], FILTERED_OUT: ['🚫', 'Disaring', 'idle'], DISCOVERED: ['🆕', 'Baru, belum dinilai', 'mid'],
  DRAFT_READY: ['📝', 'Draf', 'mid'], PENDING_APPROVAL: ['⏳', 'Menunggu persetujuanmu', 'mid'], APPROVED: ['👍', 'Kamu setujui', 'good'],
  REJECTED_BY_USER: ['🙅', 'Kamu tolak', 'idle'], SUBMITTING: ['📤', 'Sedang dikirim', 'mid'], SUBMITTED: ['🚀', 'Terkirim', 'good'],
  SUBMIT_FAILED: ['⚠️', 'Gagal kirim', 'low'], SUBMISSION_AMBIGUOUS: ['❓', 'Belum pasti terkirim', 'mid'], VIEWED: ['👀', 'Dilihat perusahaan', 'good'],
  INTERVIEW: ['🎤', 'Interview', 'good'], OFFER: ['🏆', 'Offer!', 'good'], REJECTED_BY_COMPANY: ['💔', 'Ditolak perusahaan', 'low'],
  NO_RESPONSE: ['🔕', 'Tidak ada respons', 'idle'], WITHDRAWN: ['↩️', 'Dibatalkan', 'idle'], NEW: ['🆕', 'Baru', 'mid'], INTERESTED: ['💛', 'Kamu minati', 'good'],
};
const REASON = [[/relevance/, 'Skill kurang cocok'], [/remote/, 'Bukan full remote'], [/old/, 'Lowongan sudah lama'], [/region/, 'Terbatas wilayah'], [/role/, 'Bukan bidangmu'], [/exclu|block/, 'Masuk daftar hindari']];
const tagEl = code => { const [i, t, c] = TAG[code] || ['•', code, 'idle']; return el('span', 'tag ' + c, `${i} ${t}`); };

let resultsOpen = false, resultsFor = null;
export function toggleResults(v = !resultsOpen, c = resultsFor || staff[0]) {
  resultsOpen = v; $('results').classList.toggle('show', v);
  if (v) showResults(c);
}
$('bResults').onclick = () => toggleResults();
$('resultsClose').onclick = () => toggleResults(false);
$('results').onclick = e => { if (e.target === $('results')) toggleResults(false); };
$('cResults').onclick = () => chatWith && toggleResults(true, chatWith);
async function showResults(c) {
  resultsFor = c;
  $('resultsChips').replaceChildren(...staff.map(s => {
    const b = el('button', 'chipb' + (s === c ? ' on' : ''), `${MOODS[s.mood].emo} ${s.name}`); b.title = s.def.role;
    b.onclick = () => showResults(s); return b;
  }));
  $('resultsChips').querySelector('.on')?.scrollIntoView({ block: 'nearest', inline: 'center' });
  const face = el('div', 'face', MOODS[c.mood].emo); face.style.cssText = faceStyle(c);
  const info = el('div'); info.append(el('div', 'jt', `${c.name} · ${c.def.role}`));
  const st = el('div', 'stars'); st.innerHTML = starsHtml(c.perfNow.score); info.append(st);
  $('resultsWho').replaceChildren(face, info);
  const list = $('resultsList');
  if (!store.live) { list.replaceChildren(el('div', 'empty', `🔌 ${OFFLINE} untuk melihat hasil kerja asli`)); return; }
  list.replaceChildren(el('div', 'empty', '⏳ Memuat…'));
  let items = [];
  try { items = (await (await fetch('results.json?' + viewFor(c), { cache: 'no-store' })).json()).items; }
  catch { list.replaceChildren(el('div', 'empty', 'Gagal memuat, coba lagi')); return; }
  if (resultsFor !== c) return;
  const view = viewFor(c);
  list.replaceChildren(...(items.length ? items.map(i => resultCard(i, view)) : [el('div', 'empty', `🌱 ${c.name} belum punya hasil kerja. ${c.def.hunt ? 'Suruh dia mencari lewat kartunya.' : ''}`)]));
}
function resultCard(i, view) {
  const card = el('div', 'job'), title = el('div', 'jt');
  if (i.url) { const a = el('a', null, i.title); a.href = i.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; title.append(a); } else title.textContent = i.title;
  card.append(title, el('div', 'jc', i.sub || ''));
  const meta = el('div', 'meta');
  if (view.includes('tracking') && i.detail) meta.append(tagEl(i.detail), el('span', null, '→'));
  meta.append(tagEl(i.tag));
  if (i.tag === 'FILTERED_OUT' && i.detail) meta.append(el('span', 'tag idle', (REASON.find(([r]) => r.test(i.detail)) || [0, i.detail])[1]));
  if (view.includes('leads')) meta.append(el('span', 'tag', i.detail === 'source_code' ? '💾 Source code' : '💼 Proyek'));
  if (view.includes('applied') && i.detail === 'manual') meta.append(el('span', 'tag', '✋ Kamu kirim sendiri'));
  if (i.score != null && !view.includes('leads')) { const s = el('span', 'stars'); s.style.fontSize = '13px'; s.innerHTML = starsHtml(clamp(i.score, 0, 1)); s.title = 'Kecocokan'; meta.append(s); }
  if (i.when) meta.append(el('span', null, '🕒 ' + ago(i.when)));
  card.append(meta);
  if (view.includes('drafts') && i.detail) { const det = el('details'); det.append(el('summary', null, '✍️ Baca surat lamarannya'), el('p', 'letter', i.detail)); card.append(det); }
  return card;
}
