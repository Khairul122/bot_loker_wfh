// ---------- freelance project board: list, interest, Cora's draft + revision, approve & submit ----------
import { store } from '../core/store.js';
import { $, el, ago, get, post, toast, OFFLINE } from './dom.js';
import { loadPrefs, savePrefNow } from '../systems/prefs.js';

const SOURCES = [['', '✨ Semua'], ['freelancer', '🌍 Freelancer'], ['projects.co.id', '🏠 Projects.co.id'], ['telegram', '🏠 Telegram']];
const VIEWS = [['all', '📋 Aktif'], ['new', '🆕 Baru'], ['interested', '⭐ Diminati'], ['proposal', '📝 Draf'], ['approved', '🚀 Disetujui'], ['old', '🕰️ Lama'], ['ignored', '🚫 Diabaikan']];
const STATUS = {
  NEW: ['good', '🆕 Baru'], INTERESTED: ['mid', '⭐ Diminati'], IGNORED: ['low', '🚫 Diabaikan'],
  APPROVED: ['mid', '⏳ Faris sedang mengisi & mengirim'], SUBMITTED: ['good', '✅ Terkirim'],
};
let boardOpen = false, source = '', view = 'all', current = null, browserFill = false, tabSources = ['freelancer', 'projects.co.id', 'telegram'];

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
  browserFill = !!data.browser_fill;
  if (data.tab_sources) tabSources = data.tab_sources;
  if (!data.items.length) { list.replaceChildren(el('div', 'empty', 'Belum ada proyek')); return; }
  list.replaceChildren(...data.items.map(lead));
}

// ---- owner actions on a lead (all stored in Supabase through the office server) ----
async function act(l, action, body = {}) {
  const r = await post(`leads/${encodeURIComponent(l.id)}/${action}`, body);
  if (r.ok) return r.data;
  const why = r.data?.error === 'llm_unavailable' ? 'Model AI belum menjawab, coba lagi' : (r.data?.error || (r.status ? `HTTP ${r.status}` : 'server tidak terjangkau'));
  toast('❌ ' + why);
  return null;
}
function applyResult(l, action, d) {
  if (d.status) l.status = d.status;
  if (d.proposal !== undefined) { l.proposal = d.proposal; l.bid_terms = d.bid_terms || null; if (l.status === 'NEW') l.status = 'INTERESTED'; }
  else if (d.bid_terms !== undefined) l.bid_terms = d.bid_terms;
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
  const [cls, label] = STATUS[l.status] || ['mid', l.status];
  const meta = el('div', 'meta', [el('span', null, '🕒 ' + (ago(l.posted_at || l.fetched_at) || '—')), el('span', `tag ${cls}`, label)]);
  if (l.proposal) meta.append(el('span', 'tag mid', '📝 Ada draf'));
  if (l.bid_auto) meta.append(el('span', 'tag good', '🤖 Dikirim otomatis'));
  if (l.bid_error) meta.append(el('span', 'tag low', '⚠️ Ditolak platform'));

  const quick = el('div', 'lead-actions');
  const star = el('button', 'btn', l.status === 'INTERESTED' ? '↩️ Batal minat' : '⭐ Minati');
  star.onclick = async e => {
    e.stopPropagation();
    const action = l.status === 'INTERESTED' ? 'new' : 'interested';
    const d = await act(l, action); if (d) { applyResult(l, action, d); render(); }
  };
  const skip = el('button', 'btn', l.status === 'IGNORED' ? '↩️ Kembalikan' : '🚫 Abaikan');
  skip.onclick = async e => {
    e.stopPropagation();
    const action = l.status === 'IGNORED' ? 'new' : 'ignored';
    const d = await act(l, action); if (d) { applyResult(l, action, d); render(); }
  };
  if (!['APPROVED', 'SUBMITTED'].includes(l.status)) quick.append(star, skip);

  card.append(top, title, meta, quick);
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

  const [cls, label] = STATUS[l.status] || ['mid', l.status];
  const grid = el('div', 'periods');
  grid.append(
    row('Sumber', l.source),
    row('Jenis', l.kind),
    row('Budget', l.budget),
    row('Status', label),
    row('Diposting', ago(l.posted_at || l.fetched_at)),
    row('Diambil', ago(l.fetched_at)),
  );
  wrap.append(grid);
  if (l.description) wrap.append(el('h4', null, 'Deskripsi'), el('p', 'note', l.description));

  const locked = ['APPROVED', 'SUBMITTED'].includes(l.status);
  const refresh = () => detail(l);
  const run = async (button, text, action, body, after) => {
    button.disabled = true; const keep = button.textContent; button.textContent = text;
    const d = await act(l, action, body);
    if (d) { applyResult(l, action, d); after?.(d); }
    refresh();
    button.disabled = false; button.textContent = keep;
  };

  if (l.bid_error) wrap.append(el('p', 'note', '⚠️ Bid otomatis ditolak: ' + l.bid_error + ' — perbaiki lalu Setujui & kirim manual.'));
  if (l.bid_auto && l.bid_submitted_at) wrap.append(el('p', 'note', '🤖 Dikirim otomatis ' + ago(l.bid_submitted_at) + '.'));

  // interest
  const decide = el('div', 'lead-actions');
  if (!locked) {
    const star = el('button', 'btn', l.status === 'INTERESTED' ? '↩️ Batal minat' : '⭐ Minati');
    star.onclick = () => run(star, '⏳…', l.status === 'INTERESTED' ? 'new' : 'interested', {});
    const skip = el('button', 'btn', l.status === 'IGNORED' ? '↩️ Kembalikan ke Baru' : '🚫 Abaikan');
    skip.onclick = () => run(skip, '⏳…', l.status === 'IGNORED' ? 'new' : 'ignored', {});
    decide.append(star, skip);
  }
  const open = document.createElement('a');
  open.className = 'btn'; open.href = l.url; open.target = '_blank'; open.rel = 'noopener noreferrer';
  open.textContent = '🌐 Buka proyek';
  decide.append(open);
  wrap.append(decide);

  // Cora's draft: edit, revise, regenerate
  wrap.append(el('h4', null, '📝 Draf proposal Cora'));
  const text = el('textarea', 'bid-text');
  text.rows = 9; text.value = l.proposal || ''; text.disabled = locked;
  text.placeholder = 'Belum ada draf. Minta Cora menulis di bawah.';
  wrap.append(text);
  if (!locked) {
    const edit = el('div', 'lead-actions');
    const write = el('button', 'btn', l.proposal ? '🔄 Tulis ulang oleh Cora' : '✍️ Minta Cora menulis draf');
    write.onclick = () => run(write, '⏳ Cora menulis…', 'proposal', {});
    const save = el('button', 'btn', '💾 Simpan editan saya');
    save.onclick = () => text.value.trim().length >= 20 ? run(save, '⏳…', 'proposal', { text: text.value }) : toast('Tulis dulu isi drafnya');
    edit.append(write, save);
    wrap.append(edit);
    if (l.proposal) {
      const note = el('input', 'bid-note');
      note.type = 'text'; note.maxLength = 500; note.placeholder = 'Catatan revisi, mis. "lebih singkat, sebut pengalaman Laravel"';
      const revise = el('button', 'btn', '🛠️ Minta revisi');
      revise.onclick = () => note.value.trim() ? run(revise, '⏳ Cora merevisi…', 'revise', { note: note.value }, () => toast('✅ Draf direvisi Cora')) : toast('Tulis catatan revisinya dulu');
      wrap.append(el('div', 'lead-actions revise', [note, revise]));
    }
  }

  // bid terms: price comes from the project's average bid / budget; the owner can correct everything
  if (l.proposal || l.bid_terms) {
    wrap.append(el('h4', null, '💰 Ajuan bid & tenggang waktu'));
    const t = l.bid_terms || {};
    const field = (label, key, type = 'text') => {
      const input = el(type === 'area' ? 'textarea' : 'input', 'bid-note');
      if (type === 'area') input.rows = 2; else input.type = 'text';
      input.value = t[key] || ''; input.disabled = locked; input.inputMode = type === 'text' ? 'decimal' : 'text';
      return [el('label', 'term', [el('span', null, label), input]), input];
    };
    const [amountRow, amount] = field('Harga penawaran (mata uang proyek)', 'amount');
    const [daysRow, days] = field('Tenggang waktu (hari)', 'duration_days');
    const [weeklyRow, weekly] = field('Batas jam per minggu (proyek per jam)', 'weekly_limit');
    const [mileRow, miles] = field('Milestone', 'milestones', 'area'); miles.inputMode = 'text';
    wrap.append(el('div', 'terms', [amountRow, daysRow, weeklyRow, mileRow]));
    if (!locked) {
      const saveTerms = el('button', 'btn', '💾 Simpan ajuan bid');
      saveTerms.onclick = () => run(saveTerms, '⏳…', 'terms',
        { amount: amount.value, duration_days: days.value, weekly_limit: weekly.value, milestones: miles.value, hourly_rate: l.bid_terms?.hourly_rate ? amount.value : '' },
        () => toast('✅ Ajuan bid tersimpan'));
      wrap.append(el('div', 'lead-actions', [saveTerms]));
      wrap.append(el('p', 'note', 'Harga diisi dari rata-rata bid platform (atau tengah budget klien), tidak di bawah rata-rata. Ubah kalau perlu lalu simpan sebelum menyetujui.'));
    }
  }

  // approve -> Faris fills the real form and presses submit
  if (l.status === 'SUBMITTED') wrap.append(el('p', 'note', '✅ Bid sudah terkirim di platform.'));
  else if (l.status === 'APPROVED') wrap.append(el('p', 'note', '⏳ Faris sedang mengisi form dan menekan Kirim di Chrome kamu. Buka kembali daftar untuk melihat hasilnya.'));
  else if ((l.proposal || '').trim().length >= 100) {
    const go = el('button', 'btn ok', '✅ Setujui & kirim bid');
    let armed = null;
    go.onclick = async () => {
      if (!armed) {
        go.textContent = '⚠️ Yakin? Klik lagi: Faris mengisi form lalu menekan KIRIM';
        armed = setTimeout(() => { armed = null; go.textContent = '✅ Setujui & kirim bid'; }, 8000);
        return;
      }
      clearTimeout(armed); armed = null;
      // only the BrowserMCP fallback needs a tab; the API and the bot's own window do not
      const tab = tabSources.includes(l.source) ? window.open('about:blank', '_blank') : null;
      const d = await act(l, 'approve', {});
      const reset = () => { tab?.close(); go.textContent = '✅ Setujui & kirim bid'; };
      if (!d) { reset(); return; }
      if (d.mode === 'manual') { toast('Isi form otomatis belum aktif (FORM_ASSIST_ENABLED=true). Kirim manual lewat tombol Buka proyek.'); reset(); return; }
      if (d.mode === 'busy') { toast('Faris masih mengerjakan form lain, tunggu sebentar'); reset(); return; }
      if (d.mode === 'api') { applyResult(l, 'approve', d); toast('✅ Bid terkirim ke Freelancer lewat API'); refresh(); return; }
      if (!tab) { applyResult(l, 'approve', d); toast('🚀 Faris membuka jendela browser sendiri, mengisi dan mengirim bid. Login sekali di jendela itu bila diminta'); refresh(); return; }
      tab.location.href = l.url;
      applyResult(l, 'approve', d); toast('🚀 Tab proyek dibuka. Di tab itu klik ikon BrowserMCP > Connect, lalu Faris mengisi dan mengirim bid'); refresh();
    };
    wrap.append(go, el('p', 'note', '🔐 Pastikan Chrome sudah login di platform dan ekstensi BrowserMCP terhubung. CAPTCHA tidak pernah diselesaikan otomatis; kalau muncul, bid berhenti dan kamu selesaikan sendiri.'));
  } else wrap.append(el('p', 'note', 'Tombol kirim muncul setelah draf proposal (minimal 100 karakter) tersedia.'));

  list.replaceChildren(wrap);
}

// ---------- freelance profile (Freelancer, LinkedIn, GitHub): saved in Supabase, GitHub syncs on save and automatically ----------
const FIELDS = [['freelancer', 'acFreelancer'], ['linkedin', 'acLinkedin'], ['github', 'acGithub']];
const syncInfo = d => d.synced_at ? `🐙 ${d.repos} repo tersinkron ${ago(d.synced_at)}` : 'Belum ada repo yang tersinkron.';

function updateLinks() {
  for (const [key, go] of [['acFreelancer', 'acFreelancerGo'], ['acLinkedin', 'acLinkedinGo']]) {
    const a = $(go), url = $(key).value.trim();
    a.href = /^https:\/\//.test(url) ? url : '#';
    a.style.visibility = /^https:\/\//.test(url) ? 'visible' : 'hidden';
  }
}
FIELDS.forEach(([, id]) => { $(id).oninput = updateLinks; });

async function loadProfile() {
  const prefs = await loadPrefs();
  FIELDS.forEach(([key, id]) => { $(id).value = prefs[key] || ''; });
  updateLinks();
  const r = await get('github.json');
  if (r.ok) $('acGithubInfo').textContent = syncInfo(r.data);
}

$('acSave').onclick = async () => {
  const button = $('acSave');
  button.disabled = true;
  try {
    for (const [key, id] of FIELDS) {
      const res = await savePrefNow(key, $(id).value.trim());
      if (!res.ok) { toast(res.data?.error === 'invalid_url' ? '❌ Link harus diawali https://' : res.data?.error === 'invalid_username' ? '❌ Username GitHub tidak valid' : res.data?.error === 'unknown_pref' ? '❌ Server masih versi lama: hentikan lalu jalankan ulang python -m bot_loker_wfh office' : `❌ Gagal menyimpan ke Supabase (${res.data?.error || res.status || 'server tidak terjangkau'})`); return; }
    }
    const username = $('acGithub').value.trim();
    if (!username) { toast('✅ Profil tersimpan di Supabase'); return; }
    $('acGithubInfo').textContent = '⏳ Menyinkronkan repo GitHub…';
    const sync = await post('github/sync', { username });
    if (sync.ok) { $('acGithubInfo').textContent = syncInfo(sync.data); toast(`✅ Profil tersimpan · ${sync.data.repos} repo GitHub tersinkron`); }
    else if (sync.data?.error === 'github_user_not_found') { $('acGithubInfo').textContent = `❌ Username GitHub "${username}" tidak ditemukan. Periksa ejaannya lalu Simpan lagi.`; toast('✅ Profil tersimpan, tapi username GitHub tidak ditemukan'); }
    else { toast('✅ Profil tersimpan, tapi GitHub belum bisa dijangkau — dicoba lagi otomatis'); await loadProfile(); }
  } finally { button.disabled = false; }
};
