// ---------- spawn staff at their desks; their mood follows real performance ----------
import { store } from '../core/store.js';
import { V, rand, clamp } from '../core/util.js';
import '../buildings/tower.js'; // fills deskSeats
import { DIVS } from '../buildings/divisions.js';
import { deskSeats, seatVia } from '../buildings/floor.js';
import { Char } from './char.js';
import { LADDER } from './body.js';
import { STAFF } from './staff/index.js';

export const staff = [];
const used = {};
STAFF.forEach(def => {
  const seat = deskSeats[def.div][used[def.div] = (used[def.div] ?? -1) + 1];
  const lvl = DIVS.findIndex(d => d.id === def.div);
  const c = new Char(def.name, def.look, lvl, seat.x, seat.z);
  c.def = def; c.seat = { ...seat, level: lvl, via: seatVia(seat) }; c.ry = c.targetRy = seat.ry; c.pose = 'work';
  c.inside = { level: lvl, via: c.seat.via, at: V(seat.x, seat.z) };
  c.state = 'work'; c.timer = rand(15, 50); c.boost = 0; c.boostUntil = 0;
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
  let base = moodFor(c.perfNow);
  // the owner's ratings of past reports (stored in the DB) lift or drag the mood a step
  const rt = store.desk.ratings[c.def.id];
  if (rt && base !== 'sedih') base = LADDER[clamp(LADDER.indexOf(base) + (rt.avg >= 4 ? 1 : rt.avg <= 2 ? -1 : 0), 0, 4)];
  if (now > c.boostUntil || !c.boost) return base;
  if (base === 'sedih') return 'fokus';
  return LADDER[clamp(LADDER.indexOf(base) + c.boost, 0, 4)];
}
