// ---------- spawn staff at their desks; their mood follows real performance ----------
import { store } from '../core/store.js';
import { rand, clamp } from '../core/util.js';
import '../buildings/office.js'; // fills deskSeats
import { deskSeats } from '../buildings/registry.js';
import { Char } from './char.js';
import { LADDER } from './body.js';
import { STAFF } from './staff/index.js';
import { adjustMoodForEnergy } from '../domain/employee-state.js';

export const staff = [];
const used = {};
STAFF.forEach(def => {
  const office = def.office || def.div;
  const seat = deskSeats[office][used[office] = (used[office] ?? -1) + 1];
  const c = new Char(def.name, def.look, 0, seat.x, seat.z);
  c.def = def; c.seat = { ...seat, level: 0 }; c.ry = c.targetRy = seat.ry; c.pose = 'work';
  c.state = 'work'; c.timer = rand(15, 50); c.boost = 0; c.boostUntil = 0;
  c.energy = 78;
  c.speed = rand(2.2, 2.8);
  staff.push(c);
});
export const byId = id => staff.find(c => c.def.id === id);

function moodFor(perf) {
  if (perf.sad) return 'sedih';
  const s = perf.score;
  return s >= 0.8 ? 'semangat' : s >= 0.6 ? 'senang' : s >= 0.4 ? 'fokus' : s >= 0.2 ? 'lelah' : 'ngantuk';
}
export function staffMood(c, now) {
  if (now < (c.sadUntil || 0)) return 'sedih';
  let base = adjustMoodForEnergy(moodFor(c.perfNow), c.energy ?? 78, LADDER);
  // the owner's ratings of past reports (stored in the DB) lift or drag the mood a step
  const rt = store.desk.ratings[c.def.id];
  if (rt && base !== 'sedih') base = LADDER[clamp(LADDER.indexOf(base) + (rt.avg >= 4 ? 1 : rt.avg <= 2 ? -1 : 0), 0, 4)];
  if (now > c.boostUntil || !c.boost) return base;
  if (base === 'sedih') return 'fokus';
  return LADDER[clamp(LADDER.indexOf(base) + c.boost, 0, 4)];
}
