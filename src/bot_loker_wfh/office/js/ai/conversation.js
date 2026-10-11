// ---------- conversations: multi-turn, about real work, sometimes ending in a plan ----------
import { clock } from '../core/engine.js';
import { store } from '../core/store.js';
import { rand, pick } from '../core/util.js';
import { spots } from '../world/spots.js';
import { staff, byId } from '../characters/team.js';
import { say } from '../fx/bubbles.js';
import { night } from '../systems/night.js';
import { sendTo, goBack } from './routine.js';
import { freeSeats, goEat } from './dining.js';
import { pingSpots, joinPong } from './pong.js';
import { shareSocialKnowledge } from './reflection.js';

// who hands work to whom in the pipeline, so desk visits make sense
const HANDOFF = { reno: 'sari', rima: 'sari', gery: 'sari', leva: 'sari', kalia: 'sari', dela: 'sari', sari: 'eli', eli: 'cora',
  cora: 'tegar', lulu: 'cora', tegar: 'faris', faris: 'subi', subi: 'tara', tara: 'ivan', ivan: 'tara', lido: 'bimo', nara: 'bimo', tama: 'bimo', bimo: 'cora' };
const first = c => (c.perfNow?.lines || ['Aman semua'])[0];
function dialogFor(a, b) {
  const h = new Date().getHours(), rt = store.desk.ratings[a.def.id], order = store.desk.instructions[a.def.id];
  const topics = [
    () => [[a, `${b.name}, update nih: ${first(a)}`], [b, `Oke! Dari aku: ${first(b)}`], [a, pick(['Sip, kita kejar bareng 💪', 'Mantap, lanjut! 👍'])], [b, pick(['Gas! 🚀', 'Siap 🙌'])]],
    () => [[a, pick(['Capek juga ya hari ini 😮‍💨', 'Mata udah sepet nih 😵'])], [b, 'Ngopi dulu yuk ☕'], [a, 'Boleh! Abis ini ya'], [b, '👍'], { plan: 'kopi' }],
    () => [[a, 'Rematch pingpong nanti? 🏓'], [b, pick(['Siap kalah lagi? 😆', 'Ayo, kali ini aku menang!'])], [a, 'Lihat aja nanti 😤'], { plan: 'ping' }],
    () => [[a, h < 11 ? 'Pagi! Udah sarapan? ☀️' : h < 14 ? 'Makan siang di kantin yuk 🍛' : h < 18 ? 'Bentar lagi pulang nih 🌆' : 'Lembur nih kita 🌙'], [b, h >= 11 && h < 14 ? 'Ayo, aku lapar banget!' : 'Haha iya 😄'], { plan: h >= 11 && h < 14 ? 'makan' : null }],
    rt && (() => [[a, `Bos kasih nilai laporanku ⭐${rt.avg.toFixed(1)} lho`], [b, rt.avg >= 4 ? 'Keren! Ajarin dong caranya 🤩' : 'Semangat, nanti pasti naik 💪'], [a, rt.avg >= 4 ? 'Hehe, rajin lapor aja 😎' : 'Makasih ya 🥹']]),
    order && (() => [[a, `Bos minta aku: "${order.length > 50 ? order.slice(0, 47) + '…' : order}"`], [b, 'Oke, nanti aku bantu juga 🤝'], [a, 'Makasih! 🙏']]),
  ].filter(Boolean);
  return pick(topics)();
}
// lines play one by one; the listener turns to the speaker; a shared plan sends both off together
function converse(lines, onDone) {
  const people = [...new Set(lines.filter(Array.isArray).map(([c]) => c))];
  people.forEach(c => { c.talking = true; c.talkAt = clock.elapsedTime; });
  let i = 0;
  const step = () => {
    const ln = lines[i++];
    const apart = people.some(p => people.some(q => p.level !== q.level || p.pos.distanceTo(q.pos) > 4.5));
    if (!ln || apart) {
      people.forEach(c => c.talking = false);
      if (people.length >= 2 && Math.random() < 0.35) shareSocialKnowledge(people[0], people[1]);
      onDone && onDone();
      return;
    }
    if (!Array.isArray(ln)) { followPlan(ln.plan, people); return step(); }
    const [who, text] = ln;
    for (const o of people) if (o !== who && ['stand', 'work'].includes(o.pose) && o.state !== 'work') o.face(who.pos.x, who.pos.z);
    say(who, text, 2.8); who.doEmote(pick(['nod', 'wave', 'nod']), 1.2);
    setTimeout(step, 2400);
  };
  step();
}
function followPlan(plan, [a, b]) {
  if (!plan || !b || night) return;
  setTimeout(() => {
    const free = c => c.state === 'break' || c.state === 'work' || c.state === 'visit';
    if (!free(a) || !free(b)) return;
    if (plan === 'makan') { const seats = freeSeats(); const s1 = seats[0], s2 = seats.find(s => s !== s1 && s.table === s1?.table); if (s1 && s2) { goEat(a, s1); goEat(b, s2); } }
    if (plan === 'kopi') { const k = spots.filter(s => (s.kind === 'kopi' || s.kind === 'kafe') && !s.by); if (k.length) { a.state = b.state = 'break'; a.timer = b.timer = rand(15, 25); sendTo(a, k[0]); if (k[1]) sendTo(b, k[1]); } }
    if (plan === 'ping' && pingSpots.every(s => !s.by)) { joinPong(a, pingSpots[0]); joinPong(b, pingSpots[1]); }
  }, 600);
}
let chatterT = 6;
export function updateChatter(dt) {
  if ((chatterT -= dt) > 0) return;
  chatterT = rand(4, 8);
  const now = clock.elapsedTime;
  const idle = staff.filter(c => ['break', 'home'].includes(c.state) && !c.talking && c.spot && !c.path.length && !['play', 'lie'].includes(c.pose) && c.spot.kind !== 'toilet');
  for (const a of idle) for (const b of idle) {
    if (a === b || a.level !== b.level || a.pos.distanceTo(b.pos) > 3.5 || now - (a.talkAt || -99) < 20 || now - (b.talkAt || -99) < 20) continue;
    return converse(dialogFor(a, b));
  }
}
// now and then someone walks over to the colleague they hand work to and talks it through
let visitT = 15;
export function updateVisits(dt) {
  if (night || (visitT -= dt) > 0) return;
  visitT = rand(20, 40);
  const a = pick(staff.filter(c => c.state === 'work' && !c.talking && clock.elapsedTime - (c.talkAt || -99) > 40));
  const b = a && byId(HANDOFF[a.def.id]);
  if (!b || b.state !== 'work' || b.talking || b.path.length) return;
  a.state = 'visit';
  say(a, `Ke meja ${b.name} bentar ya`, 2);
  a.goTo(b.level, b.pos.x + 1.1, b.pos.z + 1.3, () => {
    if (a.state !== 'visit') return;
    a.face(b.pos.x, b.pos.z);
    converse(dialogFor(a, b), () => { if (a.state === 'visit') goBack(a); });
  });
}
