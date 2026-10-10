// ---------- talking to an employee: the card, real hunts, role commands, questions, instructions ----------
import * as THREE from 'three';
import { clock } from '../core/engine.js';
import { Snd } from '../core/sound.js';
import { store } from '../core/store.js';
import { V, rand, pick, clamp } from '../core/util.js';
import { MOODS } from '../characters/body.js';
import { me } from '../characters/player.js';
import { staffMood } from '../characters/team.js';
import { say } from '../fx/bubbles.js';
import { burst } from '../fx/particles.js';
import { goBack } from '../ai/routine.js';
import { pingSpots, joinPong } from '../ai/pong.js';
import { useSpot } from '../ai/owner-actions.js';
import { loadStats } from '../systems/sync.js';
import { $, post, toast, scoreColor, starsHtml, faceStyle, OFFLINE } from './dom.js';
import { openMenu } from './menu.js';
import { toggleInbox, draftMore } from './inbox.js';
import { toggleReports } from './reports.js';

export let chatWith = null;
const REACT = { semangat: 'jump', senang: 'wave', fokus: 'nod', lelah: 'sigh', sedih: 'sigh', ngantuk: 'startle' };
export function startChat(c) {
  if (c.state === 'report') { say(c, 'Bentar bos, aku antar laporan dulu 📋', 3); return; }
  endChat();
  chatWith = c; openCard(c);
  const dx = me.pos.x - c.pos.x, dz = me.pos.z - c.pos.z;
  const len = Math.hypot(dx, dz) || 1;
  const off = c.pose === 'work' ? V(c.pos.x + 1.1, c.pos.z + 1.7) : V(c.pos.x + dx / len * 1.4, c.pos.z + dz / len * 1.4);
  me.goTo(c.level, off.x, off.z, () => {
    if (chatWith !== c) return;
    me.face(c.pos.x, c.pos.z);
    if (store.fp) { store.yaw = me.targetRy; store.pitch = c.pose === 'work' ? -0.22 : -0.05; }
    c.state = 'chat'; c.path = []; c.onArrive = null;
    if (c.pose !== 'work') c.pose = c.spot ? c.spot.pose : 'stand';
    if (c.pose === 'stand') c.face(me.pos.x, me.pos.z);
    c.doEmote(REACT[c.mood], 2);
    me.doEmote('wave', 1.6);
    say(c, c.mood === 'ngantuk' ? 'Eh! Aku nggak tidur kok 😳' : pick(c.perfNow.lines));
    me.joy = clamp(me.joy + 3, 0, 100); Snd.play('pop');
  });
}
export function endChat() {
  if (!chatWith) return;
  const c = chatWith; chatWith = null; closeCard();
  if (c.state !== 'chat') return;
  if (c.pose === 'work') { c.state = 'work'; c.timer = Math.max(c.timer, 8); }
  else if (c.spot) { c.state = 'break'; c.timer = Math.max(c.timer, 6); }
  else goBack(c);
}
function act(kind) {
  const c = chatWith; if (!c) return;
  const now = clock.elapsedTime;
  const at = new THREE.Vector3(c.pos.x, c.y, c.pos.z);
  if (kind === 'pingpong') {
    if (pingSpots.every(s => s.by && s.by !== me)) { toast('Meja pingpong lagi dipakai 🏓'); return; }
    endChat(); say(c, 'Ayo bos, siapa takut! 🏓', 3); useSpot('ping');
    const other = pingSpots.find(s => !s.by); if (other) joinPong(c, other, rand(70, 100));
    return;
  }
  if (kind === 'makan') { endChat(); say(c, 'Wah ditraktir bos? Ayo! 🍛', 3); openMenu(c); return; }
  Snd.play({ sapa: 'pop', tos: 'clap' }[kind]);
  if (kind === 'sapa') { me.doEmote('wave'); c.doEmote('wave'); say(c, pick(['Haii! 👋', 'Halo bos!', 'Eh, ada kamu 😄'])); burst(at, ['✨'], 4); c.boost = 1; me.joy += 4; }
  if (kind === 'tos') { me.doEmote('high5', 1.4); c.doEmote('high5', 1.4); setTimeout(() => { c.doEmote('cheer', 1.5); burst(at, ['✋', '✨', '⭐'], 8); }, 500); say(c, pick(['Toss! ✋', 'Yeay kompak!', 'Mantap!'])); c.boost = 2; me.joy += 8; }
  me.joy = clamp(me.joy, 0, 100);
  c.boostUntil = now + 60;
  c.setMood(staffMood({ ...c, state: 'x' }, now)); c.showEmo({ sapa: '😄', tos: '🙌' }[kind]);
  openCard(c);
}

let cardFor = null;
export function openCard(c) {
  const p = c.perfNow;
  $('cFace').textContent = MOODS[c.mood].emo; $('cFace').style.cssText = faceStyle(c);
  $('cName').textContent = c.name; $('cRole').textContent = c.def.role;
  $('cRing').style.setProperty('--p', Math.round(p.score * 100)); $('cRing').style.setProperty('--c', scoreColor(p.score));
  $('cMood').textContent = MOODS[c.mood].emo; $('cMood').title = MOODS[c.mood].label;
  $('cStars').innerHTML = starsHtml(p.score);
  const rt = store.desk.ratings[c.def.id], order = store.desk.instructions[c.def.id];
  $('cPills').innerHTML = p.pills.map(([i, v]) => `<span class="pill">${i} ${v}</span>`).join('') + `<span class="pill">${MOODS[c.mood].label}</span>`
    + (rt ? `<span class="pill" title="Rata-rata nilaimu untuk laporannya">⭐ ${rt.avg.toFixed(1)}</span>` : '') + (order ? '<span class="pill" title="Punya instruksi darimu">📝</span>' : '');
  const h = c.def.hunt, cmd = ROLE_CMD[c.def.id];
  $('cHuntBtn').style.display = h || cmd ? 'block' : 'none';
  if (h) {
    $('cHuntBtn').disabled = !!hunting;
    $('cHuntBtn').textContent = hunting === c ? `⏳ ${c.name} lagi mencari…` : hunting ? `⏳ ${hunting.name} lagi mencari, tunggu ya`
      : `🔎 ${c.lastHunt ? 'Cari lagi' : `Cari ${h.what} di ${h.site} sekarang`}`;
  } else if (cmd) { $('cHuntBtn').disabled = !!c.cmdBusy; $('cHuntBtn').textContent = c.cmdBusy ? '⏳ Sedang dikerjakan…' : cmd[0]; }
  if (cardFor !== c) {
    cardFor = c;
    ['cAsk', 'cOrder'].forEach(id => $(id).classList.remove('show'));
    ['cAskBtn', 'cOrderBtn'].forEach(id => $(id).classList.remove('on'));
    $('cAnswer').textContent = ''; $('cAskIn').value = '';
    $('cOrderIn').value = order || ''; $('cOrderHint').textContent = ORDER_HINT(c);
  }
  showLeads(c.lastHunt || []);
  $('cBoard').style.display = h?.what === 'proyek' ? 'flex' : 'none';
  $('card').classList.add('show');
}
function closeCard() { $('card').classList.remove('show'); }
$('cardClose').onclick = endChat;
document.querySelectorAll('[data-act]').forEach(b => b.onclick = () => act(b.dataset.act));

// ---------- real hunt: employees run the bot's own fetchers ----------
let hunting = null; // the employee currently searching (server runs one search at a time)
function showLeads(list) {
  $('cHunt').replaceChildren(...list.map(l => {
    const li = document.createElement('li'), a = document.createElement('a'), sm = document.createElement('small');
    a.href = l.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.textContent = ({ source_code: '💾 ', job: '🏢 ' }[l.kind] || '💼 ') + l.title;
    sm.textContent = l.sub || (l.kind === 'job' ? 'Remote' : 'Budget belum ditulis');
    a.appendChild(sm); li.appendChild(a); return li;
  }));
}
async function hunt(c) {
  const h = c.def.hunt;
  if (!h || hunting) return;
  if (!store.live) { toast(`${OFFLINE} supaya karyawan bisa mencari beneran`); return; }
  hunting = c; if (chatWith) openCard(chatWith);
  c.showEmo('🔎'); say(c, `Bentar ya, aku cek ${h.site}… 🔎`, 120);
  Snd.play('click');
  let res;
  try { const r = await fetch('hunt/' + h.src, { method: 'POST' }); res = r.ok ? await r.json() : { error: r.status }; }
  catch { res = { error: 'offline' }; }
  hunting = null;
  const at = new THREE.Vector3(c.pos.x, c.y, c.pos.z);
  if (res.error) {
    c.sadUntil = clock.elapsedTime + 20; c.doEmote('sigh', 2.5); Snd.play('sad');
    say(c, res.error === 409 ? 'Ada yang lagi nyari, gantian ya 🙏'
      : res.error === 404 ? 'Aku belum dikasih daftar channel. Isi LEAD_TELEGRAM_CHANNELS di .env lalu jalankan ulang office ya 📋'
      : `Gagal nyambung ke ${h.site} 😢 coba lagi nanti`, 8);
  } else {
    c.lastHunt = res.top;
    if (res.matched > 0) {
      c.boost = 2; c.boostUntil = clock.elapsedTime + 90; c.doEmote('cheer', 2.5);
      burst(at, [h.what === 'proyek' ? '💼' : '🏢', '✨', '🎉'], 10); Snd.play('coin');
      say(c, `Dapet ${res.matched} ${h.what} baru yang cocok! 🎉`);
      toast(`${h.what === 'proyek' ? '💼' : '🏢'} ${c.name} menemukan ${res.matched} ${h.what} cocok di ${h.site}`);
      me.joy = clamp(me.joy + 10, 0, 100);
    } else if (res.inserted > 0) {
      c.doEmote('nod', 1.5); Snd.play('pop');
      say(c, `Ada ${res.inserted} ${h.what} baru, tapi belum ada yang pas buat kamu`);
    } else {
      c.doEmote('nod', 1.5); Snd.play('pop');
      say(c, `Belum ada ${h.what} baru. Ini yang terakhir aku simpan 👇`);
    }
    await loadStats();
  }
  if (chatWith) openCard(chatWith);
}
$('cHuntBtn').onclick = () => { const c = chatWith; if (!c) return; c.def.hunt ? hunt(c) : ROLE_CMD[c.def.id]?.[1](c); };

// ---------- real orders: each role's own command, reports, questions, standing instructions ----------
const ORDER_HINT = c => c.def.hunt ? 'Kata kunci prioritas: hasil pencarian yang cocok kutampilkan paling atas. Contoh: python, django, laravel'
  : c.def.id === 'sari' ? 'Kata kunci prioritas: lowongan cocok yang mengandung kata ini dibuatkan surat lebih dulu oleh Cora.'
  : c.def.id === 'cora' ? 'Ditambahkan ke setiap prompt surat lamaran & proposal. Contoh: tonjolkan pengalaman membangun REST API'
  : 'Dipakai sebagai konteks saat kamu bertanya ke karyawan ini.';
async function busyCmd(c, emo, start, run) {
  if (!store.live) { toast(OFFLINE); return; }
  c.cmdBusy = true; c.showEmo(emo); say(c, start, 60); if (chatWith === c) openCard(c);
  try { await run(); } finally { c.cmdBusy = false; if (chatWith === c) openCard(c); }
}
const screenNow = c => busyCmd(c, '🧮', 'Aku nilai antrean lowongannya sekarang 🧮', async () => {
  const res = await post('work/screen');
  if (res.ok) { c.doEmote('cheer', 2); say(c, `Selesai! ${res.data.matched} lowongan baru lolos ✅`); Snd.play('chime'); await loadStats(); }
  else { c.doEmote('sigh', 1.5); say(c, res.status === 409 ? 'Tim lagi sibuk, nanti ya 🙏' : 'Gagal menilai 😢'); }
});
const telegramNow = c => busyCmd(c, '📨', 'Aku rangkum lalu kirim ke Telegram-mu 📨', async () => {
  const res = await post('work/telegram');
  if (res.ok && res.data.sent) { c.doEmote('cheer', 2); say(c, 'Ringkasan terkirim ke Telegram-mu 📨'); Snd.play('chime'); }
  else { c.doEmote('sigh', 1.5); say(c, res.ok ? 'Telegram belum diatur: isi TELEGRAM_BOT_TOKEN & TELEGRAM_ALLOWED_CHAT_IDS di .env' : 'Telegram tidak bisa dihubungi 😢', 7); }
});
const ROLE_CMD = {
  sari: ['🧮 Nilai antrean lowongan sekarang', screenNow], eli: ['🧮 Saring antrean lowongan sekarang', screenNow],
  cora: ['✍️ Tulis 3 draf surat lamaran', () => draftMore()], lulu: ['✍️ Bantu Cora tulis 3 draf', () => draftMore()],
  tara: ['📬 Catat balasan perusahaan', () => toggleInbox(true, 'sent')], ivan: ['🎤 Lihat lamaran yang interview', () => toggleInbox(true, 'sent')],
  faris: ['📥 Buka lamaran yang disetujui', () => toggleInbox(true)], subi: ['📥 Buka lamaran yang disetujui', () => toggleInbox(true)],
  tegar: ['📨 Kirim ringkasan ke Telegram', telegramNow],
};
function togglePane(id, btn) { const on = !$(id).classList.contains('show'); $(id).classList.toggle('show', on); $(btn).classList.toggle('on', on); if (on) $(id).querySelector('input,textarea').focus(); }
$('cAskBtn').onclick = () => togglePane('cAsk', 'cAskBtn');
$('cOrderBtn').onclick = () => togglePane('cOrder', 'cOrderBtn');
$('cReport').onclick = async () => {
  const c = chatWith; if (!c) return;
  if (!store.live) { toast(OFFLINE); return; }
  const res = await post(`reports/request/${c.def.id}`);
  if (!res.ok) { toast('Gagal membuat laporan'); return; }
  say(c, 'Siap bos, aku susun laporannya lalu antar ke ruanganmu 📋', 4);
  toast(`📋 ${c.name} menyusun laporan 24 jam${res.data.telegram ? ' · terkirim juga ke Telegram' : ''}`);
  endChat(); await loadStats();
};
async function askNow() {
  const c = chatWith, q = $('cAskIn').value.trim(); if (!c || !q) return;
  if (!store.live) { toast(OFFLINE); return; }
  $('cAskGo').disabled = true; $('cAnswer').textContent = '💭 …'; c.showEmo('💭'); c.doEmote('nod', 1.5);
  const res = await post(`ask/${c.def.id}`, { question: q });
  $('cAskGo').disabled = false;
  const a = res.ok ? res.data.answer : 'Maaf bos, aku lagi nggak bisa jawab 😢';
  if (chatWith === c) $('cAnswer').textContent = a;
  say(c, a.length > 140 ? a.slice(0, 137) + '…' : a, 8); c.showEmo(res.ok ? '💡' : '😢');
}
$('cAskGo').onclick = askNow;
$('cAskIn').onkeydown = e => { if (e.key === 'Enter') askNow(); };
$('cOrderGo').onclick = async () => {
  const c = chatWith; if (!c) return;
  if (!store.live) { toast(OFFLINE); return; }
  const res = await post(`instructions/${c.def.id}`, { text: $('cOrderIn').value });
  if (!res.ok) { toast('Gagal menyimpan instruksi'); return; }
  const t = res.data.text;
  if (t) store.desk.instructions[c.def.id] = t; else delete store.desk.instructions[c.def.id];
  c.doEmote('nod', 1.5); Snd.play('pop');
  say(c, t ? `Siap bos! Aku ikuti: "${t.length > 60 ? t.slice(0, 57) + '…' : t}"` : 'Oke, instruksinya aku hapus 👌', 5);
  openCard(c);
};
$('cProfile').onclick = () => { const c = chatWith; if (c) { endChat(); toggleReports(true, c.def.id); } };
