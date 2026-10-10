// ---------- freelance project board: leads, Cora's proposals, browser form fill, sharing ----------
import { Snd } from '../core/sound.js';
import { store } from '../core/store.js';
import { byId } from '../characters/team.js';
import { say } from '../fx/bubbles.js';
import { loadStats } from '../systems/sync.js';
import { $, el, post, toast, ago, OFFLINE } from './dom.js';
import { chatWith } from './card.js';

const BOARD_SOURCES = [['', '✨ Semua'], ['freelancer', '🌍 Freelancer.com'], ['projects.co.id', '🏠 Projects.co.id'], ['telegram', '🏠 Telegram']];
const SOURCE_FLAG = { freelancer: '🌍', 'projects.co.id': '🏠', telegram: '🏠' };
const ACCT_KEY = 'kantor-loker-akun';
let boardOpen = false, boardSource = '';
let acct = {};
try { acct = JSON.parse(localStorage.getItem(ACCT_KEY) || '{}'); } catch {}
for (const [k, id] of [['freelancer', 'acFreelancer'], ['linkedin', 'acLinkedin']]) {
  const input = $(id), go = $(id + 'Go');
  const sync = () => {
    const ok = /^https:\/\//.test(input.value.trim());
    go.href = ok ? input.value.trim() : (k === 'linkedin' ? 'https://www.linkedin.com/in/' : 'https://www.freelancer.com/dashboard');
  };
  input.value = acct[k] || ''; sync();
  input.oninput = () => { acct[k] = input.value.trim(); sync(); try { localStorage.setItem(ACCT_KEY, JSON.stringify(acct)); } catch {} };
}
async function loadGithubInfo() {
  try {
    const g = await (await fetch('github.json', { cache: 'no-store' })).json();
    if (g.username && !$('acGithub').value) $('acGithub').value = g.username;
    $('acGithubInfo').textContent = g.repos
      ? `🐙 ${g.repos} repo GitHub tersimpan (sinkron ${ago(g.synced_at)}). Cora memilih repo yang paling relevan untuk setiap proposal.`
      : '🐙 Isi username GitHub lalu klik Sinkron, supaya proposal menyertakan bukti portofolio.';
  } catch {}
}
$('acGithubSync').onclick = async () => {
  const b = $('acGithubSync'), username = $('acGithub').value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9-]{0,38}$/.test(username)) { toast('Isi username GitHub yang valid'); return; }
  b.disabled = true; b.textContent = '⏳ Sinkron…';
  const res = await post('github/sync', { username });
  b.disabled = false; b.textContent = '🔄 Sinkron';
  if (!res.ok) { toast(res.status === 400 ? 'Username GitHub tidak valid' : 'GitHub tidak bisa dihubungi, coba lagi'); Snd.play('sad'); return; }
  const c = byId('cora'); c.doEmote('cheer', 2); say(c, `${res.data.repos} repo-mu sudah aku pelajari 📚`); Snd.play('coin');
  toast(`🐙 ${res.data.repos} repo GitHub tersimpan untuk bahan proposal`);
  loadGithubInfo();
};
export function toggleBoard(v = !boardOpen, source = boardSource) {
  boardOpen = v; $('board').classList.toggle('show', v);
  if (v) { renderBoard(source); if (store.live) loadGithubInfo(); }
}
$('bBoard').onclick = () => toggleBoard();
$('boardClose').onclick = () => toggleBoard(false);
$('board').onclick = e => { if (e.target === $('board')) toggleBoard(false); };
$('cBoard').onclick = () => chatWith && toggleBoard(true, chatWith.def.hunt.src);
const BOARD_VIEWS = [['all', '📋 Semua aktif'], ['new', '🆕 Baru (≤3 hari)'], ['old', '🕰️ Lama'], ['interested', '💛 Diminati'], ['proposal', '✍️ Ada draf bid'], ['ignored', '🙈 Diabaikan']];
let boardView = 'all';
function paintBoardViews(counts) {
  $('boardViews').replaceChildren(...BOARD_VIEWS.map(([v, label]) => {
    const b = el('button', 'chipb' + (v === boardView ? ' on' : ''), counts ? `${label} · ${counts[v] ?? 0}` : label);
    b.onclick = () => { boardView = v; renderBoard(boardSource); }; return b;
  }));
}
async function renderBoard(source = boardSource) {
  boardSource = source;
  $('boardSources').replaceChildren(...BOARD_SOURCES.map(([src, label]) => {
    const b = el('button', 'chipb' + (src === source ? ' on' : ''), label); b.onclick = () => renderBoard(src); return b;
  }));
  paintBoardViews();
  const list = $('boardList');
  if (!store.live) { list.replaceChildren(el('div', 'empty', `🔌 ${OFFLINE}`)); return; }
  list.replaceChildren(el('div', 'empty', '⏳ Memuat proyek…'));
  let d;
  try {
    const r = await fetch(`leads.json?view=${boardView}` + (source ? '&source=' + encodeURIComponent(source) : ''), { cache: 'no-store' });
    if (r.status === 404) { list.replaceChildren(el('div', 'empty', '🔄 Server office masih versi lama. Hentikan (Ctrl+C) lalu jalankan ulang: python -m bot_loker_wfh office')); return; }
    d = await r.json();
  } catch { list.replaceChildren(el('div', 'empty', 'Gagal memuat, coba lagi')); return; }
  if (boardSource !== source) return;
  paintBoardViews(d.counts);
  list.replaceChildren(...(d.items.length ? d.items.map(l => leadCard(l, d.browser_fill)) : [el('div', 'empty', boardView === 'all' ? '🌱 Belum ada proyek. Suruh Lido, Nara atau Tama mencari dari kartunya.' : '🌱 Tidak ada proyek untuk filter ini.')]));
}
async function leadPost(lead, action, body) {
  const res = await post(`leads/${encodeURIComponent(lead.id)}/${action}`, body || {});
  if (!res.ok) { Snd.play('sad'); toast('Gagal, coba lagi'); }
  return res;
}
function leadCard(l, browserFill) {
  const card = el('div', 'job'), title = el('div', 'jt'), a = el('a', null, l.title);
  a.href = l.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; title.append(a);
  card.append(title, el('div', 'jc', `${SOURCE_FLAG[l.source] || '•'} ${l.source} · ${l.budget || 'Budget belum ditulis'}`));
  const meta = el('div', 'meta');
  if (l.status === 'INTERESTED') meta.append(el('span', 'tag good', '💛 Kamu minati'));
  else if (l.proposal) meta.append(el('span', 'tag mid', '✍️ Draf bid dari Cora'));
  if (l.kind === 'source_code') meta.append(el('span', 'tag', '💾 Source code'));
  meta.append(el('span', null, '🕒 ' + ago(l.posted_at || l.fetched_at)));
  card.append(meta);
  if (l.description) { const det = el('details'); det.append(el('summary', null, '📄 Deskripsi proyek'), el('p', 'letter', l.description)); card.append(det); }

  // proposal: Cora drafts it, the owner edits it
  const prop = el('div');
  const showProposal = text => {
    const ta = el('textarea', 'proposal'); ta.value = text; ta.setAttribute('aria-label', 'Proposal');
    const row = el('div', 'jact');
    const save = el('button', 'btn', '💾 Simpan proposal');
    save.onclick = async () => { save.disabled = true; if ((await leadPost(l, 'proposal', { text: ta.value })).ok) { l.proposal = ta.value; toast('💾 Proposal tersimpan'); Snd.play('pop'); } save.disabled = false; };
    const copy = el('button', 'btn', '📋 Salin');
    copy.onclick = async () => { try { await navigator.clipboard.writeText(ta.value); toast('📋 Proposal disalin, tinggal tempel di form bid'); } catch { ta.select(); } };
    row.append(save, copy);
    prop.replaceChildren(ta, row);
  };
  if (l.proposal) showProposal(l.proposal);

  const acts = el('div', 'jact');
  const btn = (text, cls, fn) => { const b = el('button', 'btn ' + cls, text); b.onclick = () => fn(b); acts.append(b); return b; };
  if (!l.proposal) btn('✍️ Minta Cora tulis proposal', 'ok', async b => {
    b.disabled = true; b.textContent = '⏳ Cora sedang menulis…';
    const c = byId('cora'); c.showEmo('✍️'); say(c, 'Aku tulis proposalnya ya ✍️', 20);
    const res = await leadPost(l, 'proposal');
    if (!res.ok) { b.disabled = false; b.textContent = '✍️ Minta Cora tulis proposal'; return; }
    l.proposal = res.data.proposal; l.status = 'INTERESTED';
    c.doEmote('cheer', 2); say(c, 'Proposal siap! Cek dan edit sesukamu 📝'); Snd.play('chime');
    showProposal(l.proposal); b.remove();
  });
  btn(l.status === 'INTERESTED' ? '💔 Batal minat' : '💛 Minati', '', async b => {
    const next = l.status === 'INTERESTED' ? 'new' : 'interested';
    if ((await leadPost(l, next)).ok) { l.status = next.toUpperCase(); b.textContent = l.status === 'INTERESTED' ? '💔 Batal minat' : '💛 Minati'; Snd.play('pop'); loadStats(); }
  });
  if (l.status === 'IGNORED') btn('↩️ Kembalikan', '', async () => { if ((await leadPost(l, 'new')).ok) { card.remove(); Snd.play('pop'); loadStats(); } });
  else btn('🙈 Abaikan', 'no', async () => { if ((await leadPost(l, 'ignored')).ok) { card.remove(); Snd.play('pop'); loadStats(); } });
  const open = el('a', 'btn', '🌐 Buka & apply'); open.href = l.url; open.target = '_blank'; open.rel = 'noopener noreferrer'; acts.append(open);
  if (browserFill) {
    for (const [engine, label] of [['browsermcp', '🧾 Isi di Chrome-ku'], ['playwright', '🎭 Isi pakai Playwright']]) {
      btn(label, '', async b => {
        if (!l.proposal) { toast('✍️ Tulis proposal dulu, lalu form bid bisa diisi otomatis'); return; }
        b.disabled = true;
        const res = await leadPost(l, 'fill', { engine });
        b.disabled = false;
        if (!res.ok) return;
        if (res.data.mode === 'busy') { toast('🪟 Jendela pengisi form sebelumnya masih terbuka. Selesaikan atau tutup dulu jendela itu'); return; }
        const f = byId('faris'); f.showEmo('🧾'); f.doEmote('cheer', 2); Snd.play('chime');
        say(f, engine === 'playwright' ? 'Aku buka jendela Playwright & isi form bid-nya. Kamu yang klik kirim ya 🎭' : 'Aku isi form bid di Chrome-mu. Cek lalu kamu yang klik kirim ya 🧾', 8);
        toast(engine === 'playwright'
          ? '🎭 Jendela Playwright terbuka. Kalau diminta, login di jendela itu: form langsung diisi setelah login. Kamu yang klik kirim'
          : '🧾 Pastikan ekstensi BrowserMCP di Chrome sudah Connect. Form diisi, kamu yang klik kirim');
      });
    }
  }
  const shareRow = el('div', 'share');
  btn('📤 Bagikan', '', () => shareRow.classList.toggle('show'));
  const text = `${l.title} (${l.budget || 'budget belum ditulis'})`;
  const enc = encodeURIComponent;
  for (const [label, url] of [
    ['💬 WhatsApp', `https://wa.me/?text=${enc(text + '\n' + l.url)}`],
    ['✈️ Telegram', `https://t.me/share/url?url=${enc(l.url)}&text=${enc(text)}`],
    ['💼 LinkedIn', `https://www.linkedin.com/sharing/share-offsite/?url=${enc(l.url)}`],
  ]) { const s = el('a', 'btn', label); s.href = url; s.target = '_blank'; s.rel = 'noopener noreferrer'; shareRow.append(s); }
  const cp = el('button', 'btn', '🔗 Salin link');
  cp.onclick = async () => { try { await navigator.clipboard.writeText(l.url); toast('🔗 Link disalin'); } catch {} };
  shareRow.append(cp);
  if (navigator.share) { const ns = el('button', 'btn', '📱 Lainnya'); ns.onclick = () => navigator.share({ title: l.title, text, url: l.url }).catch(() => {}); shareRow.append(ns); }
  card.append(prop, acts, shareRow);
  return card;
}
