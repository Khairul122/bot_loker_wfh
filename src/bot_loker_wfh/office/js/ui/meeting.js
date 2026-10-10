// ---------- interactive dynamic meeting room: pick topic + crew, run via 9Router ----------
import { store } from '../core/store.js';
import { staff, byId } from '../characters/team.js';
import { me } from '../characters/player.js';
import { spots } from '../world/spots.js';
import { say } from '../fx/bubbles.js';
import { sendTo, goBack } from '../ai/routine.js';
import { pick } from '../core/util.js';
import { $, el, post, toast } from './dom.js';

const DEFAULT = ['cora', 'tegar', 'reno'];
const picked = new Set(DEFAULT.filter(id => staff.some(c => c.def.id === id)));
let busy = false;
let activeRun = null; // { crew, streamed }

export function toggleMeeting(v = !$('meeting').classList.contains('show')) {
  $('meeting').classList.toggle('show', v);
  if (v) { $('meeting').classList.toggle('live', busy); render(); }
}
export function openMeeting() { toggleMeeting(true); }

$('meetingClose').onclick = () => toggleMeeting(false);
$('meeting').onclick = e => { if (e.target === $('meeting')) toggleMeeting(false); };

function render() {
  $('meetingPeople').replaceChildren(...staff.map(c => {
    const b = el('button', 'chipb' + (picked.has(c.def.id) ? ' on' : ''), c.def.name);
    b.title = c.def.role;
    b.onclick = () => { picked.has(c.def.id) ? picked.delete(c.def.id) : picked.add(c.def.id); render(); };
    return b;
  }));
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
const nameOf = id => byId(id)?.name || id;
const line = text => { const l = $('meetingLog'); if (l) l.append(el('li', null, text)); };

// walk the picked crew to the meeting table so the discussion is visible in 3D.
// Returns promises that settle once each character has actually sat down (or a safety timeout fires).
function gather(crew) {
  const seats = spots.filter(s => s.kind === 'rapat' && s.emo !== '👑' && !s.by);
  const waits = [];
  crew.forEach(c => {
    const s = seats.shift();
    if (!s) return;
    if (c.state !== 'chat') { c.state = 'chat'; c.leaveSpot(); }
    waits.push(new Promise(resolve => {
      let done = false; const fin = () => { if (!done) { done = true; resolve(); } };
      sendTo(c, s, () => { c.showEmo('💬'); fin(); });
      setTimeout(fin, 10000); // never hang the run if a seat is somehow taken
    }));
  });
  const head = spots.find(s => s.kind === 'rapat' && s.emo === '👑' && !s.by);
  if (head && me.spot?.kind !== 'rapat') sendTo(me, head, () => say(me, 'Rapat dimulai 💬'));
  return waits;
}

// one turn: the speaker gestures, everyone else turns to listen and nods now and then
function speak(emp, text) {
  if (!text) return;
  line(${nameOf(emp)}: );
  const c = byId(emp);
  if (!c) return;
  const seated = activeRun ? activeRun.crew : [];
  seated.forEach(o => { if (o !== c) { o.face(c.pos.x, c.pos.z); if (Math.random() < 0.6) o.doEmote('nod', 1.4); } });
  if (me.spot?.kind === 'rapat') me.face(c.pos.x, c.pos.z);
  c.doEmote(pick(['give', 'nod', 'give']), 2.4); c.showEmo('💬');
  say(c, text, Math.max(2.4, Math.min(6, text.length / 20)));
}

// while 9Router is still thinking, the table is not frozen: people glance around and ponder
function ponder(crew) {
  return setInterval(() => {
    const c = pick(crew), o = pick(crew);
    if (c.state !== 'chat' || c.path.length) return;
    if (o !== c) c.face(o.pos.x, o.pos.z);
    c.doEmote(pick(['nod', 'sigh', 'give']), 1.6); c.showEmo(pick(['🤔', '💭', '💬']));
  }, 1800);
}
// only release characters still frozen in the meeting, never override a state someone else set
function returnCrew(crew) {
  crew.forEach(c => { if (c.state === 'chat') goBack(c); });
}

function finishRun(decision) {
  const run = activeRun; if (!run) return;
  activeRun = null;
  if (decision) line(`✅ Keputusan: ${decision}`);
  busy = false; $('meetingRun').disabled = false;
  sleep(1200).then(() => returnCrew(run.crew)); // let the decision land before everyone walks off
}

$('meetingRun').onclick = async () => {
  if (busy) return;
  const topic = $('meetingTopic').value.trim();
  if (!topic) return toast('Tulis topik rapatnya dulu ✍️');
  if (!picked.size) return toast('Pilih minimal satu peserta 👥');
  if (!store.live) return toast('Bot belum terhubung ke data 🟡');
  let crew = staff.filter(c => picked.has(c.def.id));
  const ready = crew.filter(c => c.state !== 'report'); // never hijack a character delivering a report
  if (ready.length < crew.length) toast('Sebagian karyawan sedang mengantar laporan, rapat jalan tanpa mereka 📋');
  crew = ready;
  if (!crew.length) return toast('Semua peserta sedang sibuk, coba lagi sebentar ⏳');
  busy = true; $('meetingRun').disabled = true; $('meeting').classList.add('live');
  $('meetingLog').replaceChildren(el('li', null, '⏳ Rapat berjalan… tim sedang berdiskusi lewat 9Router'));
  const run = { crew, streamed: false };
  activeRun = run;
  const arrivals = gather(crew);
  const thinking = ponder(crew);
  const r = await post('/api/meetings/run', { topic, participants: [...picked] });
  clearInterval(thinking);
  await Promise.race([Promise.all(arrivals), sleep(10000)]); // let them sit before anyone talks
  if (activeRun !== run) return; // a live meeting stream already finished this run
  if (!run.streamed) {
    if (!r.ok) { line('❌ Gagal menjalankan rapat. Cek koneksi 9Router di Pengaturan.'); finishRun(null); return; }
    // synchronous backend: replay the returned transcript one turn at a time
    for (const t of r.data.transcript || []) {
      if (activeRun !== run) return;
      speak(t.employee, t.speech);
      await sleep(1400 + Math.min(2600, (t.speech || '').length * 45));
    }
  }
  if (activeRun !== run) return;
  finishRun(r.ok ? r.data.decision : null);
};

// live meeting events from the office bus: {type:'meeting',meeting_id,employee,task,status,content?,participants?}
export function meetingEvent(evt) {
  if (!evt || evt.type !== 'meeting' || !evt.status) return;
  if (!activeRun) {
    // a meeting started elsewhere (e.g. backend scheduler): adopt it if we can seat its participants
    if (evt.status !== 'started') return;
    const ids = Array.isArray(evt.participants) ? evt.participants : [];
    const crew = staff.filter(c => ids.includes(c.def.id) && c.state !== 'report');
    if (!crew.length) return;
    busy = true; $('meetingRun').disabled = true; $('meeting').classList.add('live');
    $('meetingLog').replaceChildren(el('li', null, '⏳ Rapat berjalan…'));
    const run = { crew, streamed: true };
    activeRun = run;
    Promise.race([Promise.all(gather(crew)), sleep(10000)]).then(() => { if (activeRun === run) line(`🎙️ ${evt.task || 'Rapat'} dimulai`); });
    return;
  }
  activeRun.streamed = true;
  if (evt.status === 'speaking') speak(evt.employee, evt.content);
  else if (evt.status === 'completed') finishRun(evt.content);
  else if (evt.status === 'failed') { line(`❌ ${evt.content || 'Rapat gagal.'}`); finishRun(null); }
}