// ---------- interactive dynamic meeting room: pick topic + crew, run via 9Router ----------
import { store } from '../core/store.js';
import { staff } from '../characters/team.js';
import { me } from '../characters/player.js';
import { spots } from '../world/spots.js';
import { say } from '../fx/bubbles.js';
import { sendTo, goBack } from '../ai/routine.js';
import { $, el, post, toast } from './dom.js';

const DEFAULT = ['cora', 'tegar', 'reno'];
const picked = new Set(DEFAULT.filter(id => staff.some(c => c.def.id === id)));
let busy = false;

export function toggleMeeting(v = !$('meeting').classList.contains('show')) {
  $('meeting').classList.toggle('show', v);
  if (v) render();
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

// walk the picked crew to the meeting table so the discussion is visible in 3D
function gather(crew) {
  const seats = spots.filter(s => s.kind === 'rapat' && !s.by);
  crew.forEach(c => { const s = seats.shift(); if (!s) return; if (c.state !== 'chat') { c.state = 'chat'; c.leaveSpot(); } sendTo(c, s, () => c.showEmo('💬')); });
  const head = spots.find(s => s.kind === 'rapat' && s.emo === '👑' && !s.by);
  if (head && me.spot?.kind !== 'rapat') sendTo(me, head, () => say(me, 'Rapat dimulai 💬'));
}

$('meetingRun').onclick = async () => {
  if (busy) return;
  const topic = $('meetingTopic').value.trim();
  if (!topic) return toast('Tulis topik rapatnya dulu ✍️');
  if (!picked.size) return toast('Pilih minimal satu peserta 👥');
  if (!store.live) return toast('Bot belum terhubung ke data 🟡');
  busy = true; $('meetingRun').disabled = true;
  const crew = staff.filter(c => picked.has(c.def.id));
  const list = $('meetingLog');
  list.replaceChildren(el('li', null, '⏳ Rapat berjalan… tim sedang berdiskusi lewat 9Router'));
  gather(crew);
  const r = await post('/api/meetings/run', { topic, participants: [...picked] });
  if (!r.ok) {
    list.replaceChildren(el('li', null, '❌ Gagal menjalankan rapat. Cek koneksi 9Router di Pengaturan.'));
    crew.forEach(goBack);
    busy = false; $('meetingRun').disabled = false; return;
  }
  const items = (r.data.transcript || []).map(t => el('li', null, `${t.employee}: ${t.speech}`));
  items.push(el('li', null, `✅ Keputusan: ${r.data.decision}`));
  list.replaceChildren(...items);
  crew.forEach(goBack);
  busy = false; $('meetingRun').disabled = false;
};
