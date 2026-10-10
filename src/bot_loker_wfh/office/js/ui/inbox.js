// ---------- approval inbox + auto work (the server's background cycle, acted out by the team) ----------
import { clock } from '../core/engine.js';
import { Snd } from '../core/sound.js';
import { store } from '../core/store.js';
import { clamp } from '../core/util.js';
import { me } from '../characters/player.js';
import { staff, byId } from '../characters/team.js';
import { say } from '../fx/bubbles.js';
import { burst, at } from '../fx/particles.js';
import { loadStats } from '../systems/sync.js';
import { savePref } from '../systems/prefs.js';
import { $, el, post, toast, starsHtml, OFFLINE } from './dom.js';
import { TAG } from './results.js';

const fmtIn = sec => sec == null ? 'segera' : sec < 3600 ? `${Math.max(1, Math.round(sec / 60))} menit lagi` : `${Math.round(sec / 3600)} jam lagi`;
export function renderAuto() {
  const w = store.S.work || {};
  $('bAuto').classList.toggle('on', !!w.auto);
  $('bAuto').title = !store.live ? 'Butuh server office' : !w.auto ? 'Nyalakan kerja otomatis'
    : w.busy ? 'Tim lagi bekerja…' : `Tim kerja otomatis · putaran berikutnya ${fmtIn(w.next_in)}`;
}
let inboxOpen = false, lastPending = 0;
export function renderBadge() {
  const n = (store.S.applications || {}).PENDING_APPROVAL || 0;
  $('inboxBadge').textContent = n; $('inboxBadge').classList.toggle('on', n > 0);
  if (inboxOpen && n !== lastPending) renderInbox();
  lastPending = n;
  $('reportsBadge').textContent = store.desk.tray; $('reportsBadge').classList.toggle('on', store.desk.tray > 0);
}
export async function setAuto(on) {
  const res = await post('auto', { on });
  if (!res.ok) { toast(OFFLINE); return; }
  store.S.work = res.data; renderAuto();
  savePref('auto', on ? '1' : '0');
  toast(on ? '🤖 Tim kerja otomatis: cari → nilai → tulis draf. Hasilnya masuk 📥 untuk kamu setujui' : '🤖 Kerja otomatis dimatikan');
}
$('bAuto').onclick = () => store.live ? setAuto(!store.S.work?.auto) : toast(OFFLINE);

let prevBusy = null, lastWorkAt;
const workerFor = src => src === 'draft' || src === 'proposal' ? byId('cora') : staff.find(c => c.def.hunt?.src === src);
export function reactToWork() {
  const w = store.S.work; if (!w) return;
  if (w.busy !== prevBusy) {
    const c = w.busy && workerFor(w.busy);
    if (c) {
      c.showEmo(c.def.hunt ? '🔎' : '✍️');
      say(c, w.busy === 'draft' ? 'Aku tulis surat lamarannya ya ✍️' : w.busy === 'proposal' ? 'Aku tulis draf bid dari profil & GitHub-mu ✍️' : `Lagi cek ${c.def.hunt.site}… 🔎`, 8);
    }
    prevBusy = w.busy;
  }
  const L = w.last;
  if (!L || L.at === lastWorkAt) return;
  const first = lastWorkAt === undefined; lastWorkAt = L.at;
  if (first) return; // only react to work done while the office is open
  const c = workerFor(L.source); if (!c) return;
  if (L.error) { c.sadUntil = clock.elapsedTime + 20; c.doEmote('sigh', 2); say(c, 'Sumberku lagi error 😢 nanti aku coba lagi'); return; }
  if (L.matched > 0) {
    c.boost = 2; c.boostUntil = clock.elapsedTime + 90; c.doEmote('cheer', 2.5);
    burst(at(c), L.source === 'draft' ? ['✍️', '📝', '✨'] : ['🏢', '✨', '🎉'], 8); Snd.play('coin');
    say(c, L.source === 'draft' ? `${L.matched} draf siap kamu cek di 📥` : L.source === 'proposal' ? `${L.matched} draf bid siap di 💼` : `Dapet ${L.matched} yang cocok! 🎉`);
    toast(L.source === 'draft' ? `✍️ Cora menyiapkan ${L.matched} draf lamaran — cek 📥 Persetujuan`
      : L.source === 'proposal' ? `✍️ Cora menulis ${L.matched} draf bid proyek — cek 💼 Proyek` : `${c.def.hunt.what === 'proyek' ? '💼' : '🏢'} ${c.name} menemukan ${L.matched} ${c.def.hunt.what} cocok`);
  } else { c.doEmote('nod', 1.5); say(c, 'Belum ada yang baru, nanti aku cek lagi'); }
}

export async function toggleInbox(v = !inboxOpen, focus) {
  inboxOpen = v; $('inbox').classList.toggle('show', v);
  if (!v) return;
  await renderInbox();
  if (focus === 'sent') ($('inboxSent') || $('inboxList')).scrollIntoView({ block: 'start' });
}
$('bInbox').onclick = () => toggleInbox();
$('inboxClose').onclick = () => toggleInbox(false);
$('inbox').onclick = e => { if (e.target === $('inbox')) toggleInbox(false); };
async function renderInbox() {
  const L = $('inboxList');
  if (!store.live) { L.replaceChildren(el('div', 'empty', `🔌 ${OFFLINE}`)); return; }
  let d;
  try { d = await (await fetch('inbox.json', { cache: 'no-store' })).json(); } catch { L.replaceChildren(el('div', 'empty', 'Gagal memuat, coba lagi')); return; }
  $('inboxSub').textContent = d.pending.length ? `${d.pending.length} lowongan cocok menunggu keputusanmu` : 'Belum ada yang perlu kamu setujui';
  const parts = [];
  if (d.pending.length) parts.push(el('h3', null, '🕵️ Menunggu persetujuanmu'), ...d.pending.map(i => jobCard(i, 'pending', d.form_assist)));
  if (d.approved.length) parts.push(el('h3', null, '🚀 Disetujui · tinggal dilamar'), ...d.approved.map(i => jobCard(i, 'approved', d.form_assist)));
  if (d.sent?.length) { const h3 = el('h3', null, '📬 Sudah dilamar · catat balasan perusahaan (Tara)'); h3.id = 'inboxSent'; parts.push(h3, ...d.sent.map(i => jobCard(i, 'sent', d.form_assist))); }
  if (!parts.length) parts.push(el('div', 'empty', d.waiting ? '🌱 Belum ada draf. Minta Cora menulis dulu 👇' : '🌱 Kotak masih kosong. Nyalakan 🤖 Auto atau suruh tim Pencari Kerja mencari.'));
  const foot = el('div', 'foot');
  foot.append(el('span', null, d.waiting ? `✍️ ${d.waiting} lowongan cocok lain belum ada suratnya` : '✨ Semua lowongan cocok sudah ada drafnya'));
  if (d.waiting) { const b = el('button', 'btn', '✍️ Minta Cora tulis 3 draf'); b.onclick = () => { b.disabled = true; draftMore(); }; foot.append(b); }
  parts.push(foot);
  L.replaceChildren(...parts);
}
function jobCard(i, kind, formAssist) {
  const card = el('div', 'job');
  card.append(el('div', 'jt', i.title), el('div', 'jc', [i.company, i.location].filter(Boolean).join(' · ')));
  const st = el('div', 'stars'); st.innerHTML = starsHtml(clamp(i.score || 0, 0, 1)); st.title = 'Kecocokan dengan skill-mu'; card.append(st);
  if (kind === 'pending' && i.letter) { const det = el('details'); det.append(el('summary', null, '✍️ Surat lamaran dari Cora'), el('p', 'letter', i.letter)); card.append(det); }
  const row = el('div', 'jact');
  const link = el('a', 'btn', kind === 'pending' ? '👀 Lihat lowongan' : '🌐 Buka & lamar'); link.href = i.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; row.append(link);
  const btn = (text, cls, fn) => { const b = el('button', 'btn ' + cls, text); b.onclick = () => { row.querySelectorAll('button').forEach(x => x.disabled = true); fn(); }; row.append(b); };
  if (kind === 'sent') {
    card.querySelector('.jc').textContent += ` · ${(TAG[i.status] || ['', i.status])[1]}`;
    const next = { SUBMITTED: ['viewed', 'interview', 'rejected', 'noresponse'], VIEWED: ['interview', 'rejected', 'noresponse'], INTERVIEW: ['offer', 'rejected'] }[i.status] || [];
    const label = { viewed: '👀 Dilihat', interview: '🎤 Interview', offer: '🏆 Offer!', rejected: '💔 Ditolak', noresponse: '🔕 Tak ada kabar' };
    next.forEach(a => btn(label[a], a === 'offer' || a === 'interview' ? 'ok' : a === 'rejected' ? 'no' : '', () => decide(i, a)));
  }
  else if (kind === 'pending') { btn(formAssist ? '✅ Setujui & isi formulir' : '✅ Setujui & lamar', 'ok', () => decide(i, 'approve')); btn('❌ Tolak', 'no', () => decide(i, 'reject')); }
  else { if (formAssist) btn('🧾 Isi formulir lagi', '', () => decide(i, 'apply')); btn('✔️ Sudah dilamar', 'ok', () => decide(i, 'applied')); }
  card.append(row);
  return card;
}
async function decide(item, action) {
  const res = await post(`inbox/${encodeURIComponent(item.id)}/${action}`);
  if (!res.ok) { Snd.play('sad'); toast(res.status === 409 ? 'Lamaran ini sudah diproses sebelumnya' : 'Gagal, coba lagi'); await loadStats(); return renderInbox(); }
  if (action === 'approve' || action === 'apply') {
    const f = byId('faris'); f.boost = 2; f.boostUntil = clock.elapsedTime + 60; f.doEmote('cheer', 2); Snd.play('chime');
    if (res.data.mode === 'form') { f.showEmo('🧾'); say(f, 'Aku isi formulirnya di browser. Cek, lalu kamu yang klik kirim ya 🧾', 6); toast('🧾 Faris membuka & mengisi formulir di browser. Periksa, klik kirim, lalu tandai "Sudah dilamar"'); }
    else { say(f, 'Disetujui! Buka lowongannya lalu lamar ya 👉', 6); toast('✅ Disetujui. Klik "Buka & lamar", kirim lamarannya, lalu tandai "Sudah dilamar"'); }
  } else if (action === 'reject') {
    const e = byId('eli'); e.doEmote('nod', 1.5); say(e, 'Oke, yang ini aku lewati 👌'); Snd.play('pop');
  } else if (['viewed', 'interview', 'offer', 'rejected', 'noresponse'].includes(action)) {
    const t = byId('tara'), v = byId('ivan');
    if (action === 'interview' || action === 'offer') {
      [t, v].forEach(c => { c.boost = 2; c.boostUntil = clock.elapsedTime + 120; c.doEmote('cheer', 2.5); });
      burst(at(v), action === 'offer' ? ['🏆', '🎉', '💰'] : ['🎤', '✨', '🎉'], 10); Snd.play('coin');
      say(v, action === 'offer' ? 'OFFER!! Selamat bos! 🏆' : 'Interview! Yuk latihan bareng aku 🎤', 6);
    } else { t.doEmote(action === 'rejected' ? 'sigh' : 'nod', 1.5); say(t, action === 'rejected' ? 'Semangat bos, masih banyak yang lain 🤗' : 'Sudah aku catat 📒', 4); Snd.play('pop'); }
    toast('📬 Status lamaran diperbarui');
  } else if (action === 'applied') {
    const s = byId('subi'); s.boost = 2; s.boostUntil = clock.elapsedTime + 90; s.doEmote('cheer', 3); burst(at(s), ['🚀', '✨', '🎉'], 10);
    say(s, 'Lamaran terkirim! Semoga lolos 🤞', 6); Snd.play('coin'); toast('🚀 Lamaran tercatat terkirim. Tara akan memantau statusnya');
    me.joy = clamp(me.joy + 12, 0, 100);
  }
  await loadStats(); renderInbox();
}
export async function draftMore() {
  const c = byId('cora'); c.showEmo('✍️'); say(c, 'Siap, aku tulis sekarang ✍️', 30);
  const res = await post('inbox/draft');
  if (res.ok) { c.doEmote('cheer', 2); say(c, `${res.data.drafted} draf siap kamu cek!`); Snd.play('chime'); }
  else { c.doEmote('sigh', 1.5); say(c, res.status === 409 ? 'Tim lagi sibuk, sebentar lagi ya' : 'Gagal nulis 😢 coba lagi'); }
  await loadStats(); renderInbox();
}
