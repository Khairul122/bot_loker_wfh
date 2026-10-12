// ---------- reports panel: per-employee profile, report cards, owner ratings ----------
import { clock } from '../core/engine.js';
import { Snd } from '../core/sound.js';
import { store } from '../core/store.js';
import { pick, clamp } from '../core/util.js';
import { MOODS } from '../characters/body.js';
import { staff, byId } from '../characters/team.js';
import { say } from '../fx/bubbles.js';
import { loadStats } from '../systems/sync.js';
import { recordExperience } from '../ai/reflection.js';
import { $, el, toast, ago, starsHtml, faceStyle, OFFLINE } from './dom.js';
import { get, post } from '../infrastructure/office-api.js';
import { startChat } from './card.js';

let reportsOpen = false, reportsFor = '';
export function toggleReports(v = !reportsOpen, emp = reportsFor) { reportsOpen = v; $('reports').classList.toggle('show', v); if (v) renderReports(emp); }
// one employee's own panel: three periods side by side, score trend with ratings, owner notes
async function renderProfile(emp) {
  const box = $('reportsProfile');
  if (!emp || !store.live) { box.replaceChildren(); return; }
  const profile = await get('employee.json?id=' + encodeURIComponent(emp));
  if (!profile.ok) { box.replaceChildren(); return; }
  const p = profile.data;
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
  if (p.managed_division) wrap.append(await managerTeam(p.managed_division, emp));
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

async function managerTeam(division, managerId) {
  const section = el('section', 'division-team');
  section.setAttribute('aria-label', `Tim ${division.name}`);
  const manager = division.team.find(member => member.employee === division.manager);
  section.append(el('h4', null, `Tim ${division.name} · ${division.team.length} karyawan`));

  const lead = el('div', 'division-manager');
  const leadInfo = el('div');
  leadInfo.append(el('b', null, `Penanggung jawab: ${manager?.name || managerId}`));
  leadInfo.append(el('small', null, manager?.role || 'Manager divisi'));
  leadInfo.append(el('small', null, 'Brief dapat mencatat tugas internal. Submit lamaran atau bid tetap menunggu persetujuanmu.'));
  const briefButton = el('button', 'btn ok', 'Minta brief dan prioritas Hermes');
  briefButton.type = 'button';
  const briefStatus = el('p', 'division-manager-status');
  briefStatus.textContent = 'Belum ada brief baru. Hermes membaca metrik 24 jam untuk menyusun prioritas divisi.';
  briefStatus.setAttribute('role', 'status');
  briefStatus.setAttribute('aria-live', 'polite');
  briefButton.onclick = async () => {
    briefButton.disabled = true;
    briefStatus.textContent = 'Hermes sedang membaca kinerja tim dan tugas internal…';
    briefStatus.setAttribute('aria-busy', 'true');
    const response = await post('manager/brief', { manager: managerId });
    briefStatus.setAttribute('aria-busy', 'false');
    briefButton.disabled = false;
    if (!response.ok) {
      briefStatus.textContent = response.status === 503
        ? 'Hermes belum tersambung. Periksa koneksi di Pengaturan Hermes, lalu coba lagi.'
        : 'Brief belum berhasil dibuat. Coba lagi atau periksa log kantor.';
      return;
    }
    const assigned = response.data.assigned_tasks || [];
    briefStatus.textContent = assigned.length
      ? `${response.data.summary} ${assigned.length} tugas internal telah dicatat untuk tim.`
      : `${response.data.summary} Belum ada tugas baru yang perlu dicatat.`;
    await renderTasks();
  };
  lead.append(leadInfo, briefButton);
  section.append(lead, briefStatus);

  const members = el('div', 'division-members');
  for (const member of division.team) {
    const item = el('article', 'division-member');
    const heading = el('div', 'division-member-head');
    heading.append(el('b', null, member.name));
    if (member.employee === division.manager) heading.append(el('span', 'tag manager-tag', 'Manager'));
    item.append(heading, el('small', null, member.role));

    const score = document.createElement('progress');
    score.max = 1;
    score.value = Math.max(0, Math.min(1, Number(member.score) || 0));
    score.setAttribute('aria-label', `Skor ${member.name}`);
    item.append(score);
    item.append(el('p', null, member.lines.join(' ')));
    members.append(item);
  }
  section.append(members);

  const heading = el('h4', null, 'Prioritas & penugasan internal');
  const form = el('form', 'manager-task-form');
  const title = document.createElement('input');
  title.name = 'title'; title.required = true; title.minLength = 3; title.maxLength = 160;
  title.placeholder = 'Contoh: cek kualitas ringkasan kandidat'; title.setAttribute('aria-label', 'Tugas internal');
  const assignee = document.createElement('select'); assignee.name = 'assignee'; assignee.setAttribute('aria-label', 'Anggota tim');
  for (const member of division.team) {
    const option = document.createElement('option'); option.value = member.employee; option.textContent = member.name;
    assignee.append(option);
  }
  const priority = document.createElement('select'); priority.name = 'priority'; priority.setAttribute('aria-label', 'Prioritas tugas');
  for (const [value, label] of [['normal', 'Normal'], ['high', 'Tinggi'], ['low', 'Rendah']]) {
    const option = document.createElement('option'); option.value = value; option.textContent = label; priority.append(option);
  }
  const submit = el('button', 'btn ok', 'Tugaskan'); submit.type = 'submit';
  form.append(title, assignee, priority, submit);
  const tasks = el('div', 'manager-tasks');
  const renderTasks = async () => {
    const response = await get(`manager/tasks.json?id=${encodeURIComponent(managerId)}`);
    if (!response.ok) { tasks.replaceChildren(el('p', 'note', 'Koneksi ke kantor gagal memuat daftar tugas. Tutup dan buka lagi panel laporan untuk mencoba ulang.')); return; }
    tasks.replaceChildren(...(response.data.items.length ? response.data.items.map(task => {
      const item = el('article', 'manager-task');
      const top = el('div', 'manager-task-head');
      top.append(el('b', null, task.title), el('span', 'tag', `${task.assignee_name} · ${task.priority}`));
      item.append(top, el('small', null, ({ assigned: 'Ditugaskan', in_progress: 'Sedang dikerjakan', reviewed: 'Selesai ditinjau' })[task.status]));
      if (task.review_note) item.append(el('p', 'note', task.review_note));
      if (task.status !== 'reviewed') {
        const actions = el('div', 'manager-task-actions');
        if (task.status === 'assigned') {
          const start = el('button', 'btn', 'Mulai'); start.type = 'button';
          start.onclick = async () => { start.disabled = true; await post(`manager/tasks/${encodeURIComponent(task.id)}`, { manager: managerId, status: 'in_progress' }); await renderTasks(); };
          actions.append(start);
        }
        const review = el('input'); review.maxLength = 500; review.placeholder = 'Catatan tinjauan (opsional)'; review.setAttribute('aria-label', `Catatan tinjauan ${task.title}`);
        const finish = el('button', 'btn ok', 'Tinjau selesai'); finish.type = 'button';
        finish.onclick = async () => { finish.disabled = true; const result = await post(`manager/tasks/${encodeURIComponent(task.id)}`, { manager: managerId, status: 'reviewed', review_note: review.value }); if (!result.ok) toast('Tugas belum berhasil ditinjau'); await renderTasks(); };
        actions.append(review, finish); item.append(actions);
      }
      return item;
    }) : [el('p', 'note', 'Belum ada tugas internal. Buat prioritas pertama untuk timmu.')])) ;
  };
  form.onsubmit = async event => {
    event.preventDefault();
    submit.disabled = true;
    const response = await post('manager/tasks', { manager: managerId, assignee: assignee.value, title: title.value, priority: priority.value });
    submit.disabled = false;
    if (!response.ok) { toast('Tugas belum berhasil disimpan'); return; }
    title.value = ''; await renderTasks();
  };
  section.append(heading, form, tasks);
  await renderTasks();
  return section;
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
  const response = await get('reports.json' + (emp ? '?employee=' + encodeURIComponent(emp) : ''));
  if (!response.ok) { list.replaceChildren(el('div', 'empty', 'Gagal memuat, coba lagi')); return; }
  const d = response.data;
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
    recordExperience(r.employee || (c ? c.def.id : ''), { type: 'report_review', rating, note: note.value, score: r.score });
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
