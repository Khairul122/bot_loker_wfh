// ---------- reports panel: per-employee profile, report cards, owner ratings ----------
import { clock } from '../core/engine.js';
import { Snd } from '../core/sound.js';
import { store } from '../core/store.js';
import { pick, clamp } from '../core/util.js';
import { MOODS } from '../characters/body.js';
import { staff, byId } from '../characters/team.js';
import { say } from '../fx/bubbles.js';
import { loadStats } from '../systems/sync.js';
import { $, el, post, toast, ago, starsHtml, faceStyle, OFFLINE } from './dom.js';
import { startChat } from './card.js';

let reportsOpen = false, reportsFor = '';
export function toggleReports(v = !reportsOpen, emp = reportsFor) { reportsOpen = v; $('reports').classList.toggle('show', v); if (v) renderReports(emp); }
// one employee's own panel: three periods side by side, score trend with ratings, owner notes
async function renderProfile(emp) {
  const box = $('reportsProfile');
  if (!emp || !store.live) { box.replaceChildren(); return; }
  let p;
  try { p = await (await fetch('employee.json?id=' + encodeURIComponent(emp), { cache: 'no-store' })).json(); } catch { box.replaceChildren(); return; }
  if (reportsFor !== emp) return;
  const c = byId(emp), wrap = el('div', 'prof');
  const head = el('div', 'who'), face = el('div', 'face', c ? MOODS[c.mood].emo : '📊'); if (c) face.style.cssText = faceStyle(c);
  const info = el('div'); info.append(el('div', 'jt', `${c ? c.name : emp} · ${c ? c.def.role : p.role}`));
  const meta = el('div', 'meta');
  meta.append(el('span', 'tag ' + (p.rating ? (p.rating.avg >= 4 ? 'good' : p.rating.avg <= 2 ? 'low' : 'mid') : 'idle'), p.rating ? `⭐ ${p.rating.avg.toFixed(1)} dari ${p.rating.n} laporan` : '⭐ Belum dinilai'));
  if (c) meta.append(el('span', 'tag', `${MOODS[c.mood].emo} ${MOODS[c.mood].label}`));
  info.append(meta); head.append(face, info); wrap.append(head);
  const periods = el('div', 'periods');
  for (const [label, m] of Object.entries(p.periods)) {
    const col = el('div', 'period'); col.append(el('b', null, label));
    m.metrics.forEach(([i, l, v]) => { const row = el('div'); row.append(el('span', null, `${i} ${l}`), el('span', null, String(v))); col.append(row); });
    const st = el('div', 'stars'); st.style.fontSize = '13px'; st.innerHTML = starsHtml(clamp(m.score, 0, 1)); col.append(st);
    periods.append(col);
  }
  wrap.append(periods);
  if (p.history.length > 1) {
    wrap.append(el('h4', null, '📈 Tren skor laporan'));
    const n = p.history.length, X = i => 8 + i * (584 / (n - 1)), Y = s => 62 - s * 54;
    const pts = p.history.map((h, i) => `${X(i)},${Y(h.score)}`).join(' ');
    const dots = p.history.map((h, i) => h.rating ? `<circle cx="${X(i)}" cy="${Y(h.score)}" r="5" fill="${h.rating >= 4 ? '#5cb87a' : h.rating <= 2 ? '#ef8a6b' : '#f2b84b'}"><title>Nilaimu ${h.rating}</title></circle>` : '').join('');
    const svg = el('div'); svg.innerHTML = `<svg viewBox="0 0 600 70" preserveAspectRatio="none" role="img" aria-label="Tren skor"><polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="3" stroke-linejoin="round"/>${dots}</svg>`;
    wrap.append(svg);
  }
  if (p.instruction) wrap.append(el('h4', null, '📝 Instruksimu'), el('p', 'note', p.instruction));
  if (p.notes.length) { wrap.append(el('h4', null, '🗒️ Catatanmu terakhir')); p.notes.forEach(x => wrap.append(el('p', 'note', `${'★'.repeat(x.rating || 0)} ${x.note} · ${ago(x.at)}`))); }
  const row = el('div', 'jact');
  const req = el('button', 'btn ok', '📋 Minta laporan sekarang');
  req.onclick = async () => { req.disabled = true; const r = await post(`reports/request/${emp}`); req.disabled = false; if (r.ok) { toast(`📋 ${c ? c.name : emp} menyusun laporan dan berjalan ke ruanganmu`); await loadStats(); renderReports(emp); } };
  const talk = el('button', 'btn', '💬 Ajak ngobrol'); talk.onclick = () => { toggleReports(false); if (c) { store.overview = false; startChat(c); } };
  row.append(req, talk); wrap.append(row);
  box.replaceChildren(wrap);
}
$('bReports').onclick = () => toggleReports();
$('reportsClose').onclick = () => toggleReports(false);
$('reports').onclick = e => { if (e.target === $('reports')) toggleReports(false); };
$('reportsAll').onclick = async () => {
  if (!store.live) { toast(OFFLINE); return; }
  $('reportsAll').disabled = true;
  const res = await post('reports/request/all');
  $('reportsAll').disabled = false;
  if (!res.ok) { toast('Gagal membuat laporan'); return; }
  toast('📋 Semua karyawan menyusun laporan dan berjalan ke ruanganmu'); await loadStats(); renderReports();
};
async function renderReports(emp = reportsFor) {
  reportsFor = emp;
  renderProfile(emp);
  $('reportsChips').replaceChildren(...[['', '✨ Semua'], ...staff.map(c => [c.def.id, `${MOODS[c.mood].emo} ${c.name}`])].map(([id, label]) => {
    const b = el('button', 'chipb' + (id === emp ? ' on' : ''), label); b.onclick = () => renderReports(id); return b;
  }));
  const list = $('reportsList');
  if (!store.live) { list.replaceChildren(el('div', 'empty', `🔌 ${OFFLINE} untuk laporan asli`)); return; }
  let d;
  try { d = await (await fetch('reports.json' + (emp ? '?employee=' + encodeURIComponent(emp) : ''), { cache: 'no-store' })).json(); }
  catch { list.replaceChildren(el('div', 'empty', 'Gagal memuat, coba lagi')); return; }
  if (reportsFor !== emp) return;
  $('reportsTg').textContent = d.telegram ? '📨 Laporan juga dikirim ke Telegram-mu' : '📨 Telegram belum diatur (.env)';
  list.replaceChildren(...(d.items.length ? d.items.map(reportCard) : [el('div', 'empty', '🌱 Belum ada laporan. Laporan pagi dibuat otomatis jam 08.00, atau minta sekarang.')]));
}
function reportCard(r) {
  const c = byId(r.employee), card = el('div', 'job');
  const head = el('div', 'who');
  const face = el('div', 'face', c ? MOODS[c.mood].emo : '📋'); if (c) face.style.cssText = faceStyle(c);
  const info = el('div'); info.append(el('div', 'jt', `${c ? c.name : r.employee} · ${c ? c.def.role : ''}`));
  const meta = el('div', 'meta');
  meta.append(el('span', 'tag ' + (r.kind === 'daily' ? 'mid' : 'idle'), r.kind === 'daily' ? '🌅 Laporan pagi' : '🙋 Kamu minta'),
    el('span', null, `🕒 ${ago(r.created_at)} · ${r.hours} jam terakhir`));
  if (!r.delivered_at) meta.append(el('span', 'tag low', '🚶 Sedang diantar'));
  info.append(meta); head.append(face, info); card.append(head);
  const pills = el('div', 'pills'); r.metrics.forEach(([i, l, v]) => pills.append(el('span', 'pill', `${i} ${l}: ${v}`))); card.append(pills);
  card.append(el('p', 'letter', r.lines.join(' ')));
  const st = el('div', 'stars'); st.innerHTML = starsHtml(clamp(r.score, 0, 1)); st.title = 'Skor dari data'; card.append(st);
  let rating = r.rating || 0;
  const rate = el('div', 'rate'); rate.append(el('span', 'jc', 'Nilaimu: '));
  const stars = [1, 2, 3, 4, 5].map(n => { const b = el('button', null, '★'); b.setAttribute('aria-label', `Nilai ${n}`); b.onclick = () => { rating = n; paint(); }; rate.append(b); return b; });
  const paint = () => stars.forEach((b, i) => b.classList.toggle('on', i < rating)); paint();
  const note = el('textarea', 'note'); note.placeholder = 'Catatan untuk karyawan ini (opsional)'; note.maxLength = 1000; note.value = r.note || '';
  const save = el('button', 'btn ok', r.rating ? '💾 Perbarui nilai' : '💾 Simpan nilai');
  save.onclick = async () => {
    if (!rating) { toast('Pilih bintang dulu ⭐'); return; }
    save.disabled = true;
    const res = await post(`reports/${encodeURIComponent(r.id)}/review`, { rating, note: note.value });
    save.disabled = false;
    if (!res.ok) { toast('Gagal menyimpan'); return; }
    save.textContent = '💾 Perbarui nilai'; Snd.play('pop');
    if (c) {
      if (rating >= 4) { c.boost = 2; c.boostUntil = clock.elapsedTime + 120; c.doEmote('cheer', 2); say(c, pick(['Makasih bos! 🥹', 'Yeay dinilai bagus! ⭐', 'Aku makin semangat! 🔥'])); }
      else if (rating <= 2) { c.sadUntil = clock.elapsedTime + 30; c.doEmote('sigh', 2); say(c, note.value.trim() ? 'Siap bos, catatannya aku perbaiki 🙏' : 'Maaf bos, aku perbaiki 🙏'); }
      else { c.doEmote('nod', 1.5); say(c, 'Noted bos 👌'); }
    }
    toast(`⭐ Nilai untuk ${c ? c.name : r.employee} tersimpan`); loadStats();
  };
  card.append(rate, note, save);
  return card;
}
