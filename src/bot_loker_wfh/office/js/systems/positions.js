// ---------- character coordinates: saved to Supabase (via the office server) and restored on load ----------
import { rand } from '../core/util.js';
import { roomAt } from '../domain/office-plan.js';
import { isFree, snapFree } from '../world/navigation.js';
import { me } from '../characters/player.js';
import { staff } from '../characters/team.js';
import { get, post } from '../infrastructure/office-api.js';

const SAVE_EVERY_MS = 2000;
const RESTORE_SPACING = 0.7;
const r2 = n => Math.round(n * 100) / 100;
let lastSent = '';

function snapshot() {
  const at = c => ({ x: r2(c.pos.x), y: 0, z: r2(c.pos.z), yaw: r2(c.ry || 0) });
  const state = { owner: at(me), staff: {} };
  for (const c of staff) state.staff[c.def.id] = at(c);
  return state;
}

// A saved point may be blocked by a layout change or overlap another restored character.
function place(c, p, others) {
  const anchor = isFree(p) ? p : snapFree(p);
  const separated = q => isFree(q) && others.every(other => Math.hypot(other.pos.x - q.x, other.pos.z - q.z) >= RESTORE_SPACING);
  let at = separated(anchor) ? anchor : null;
  for (let ring = 1; !at && ring <= 16; ring++) {
    for (let dz = -ring; dz <= ring && !at; dz++) for (let dx = -ring; dx <= ring; dx++) {
      if (Math.max(Math.abs(dx), Math.abs(dz)) !== ring) continue;
      const q = { x: anchor.x + dx * 0.5, z: anchor.z + dz * 0.5 };
      if (separated(q)) { at = q; break; }
    }
  }
  at ||= anchor;
  c.pos.x = at.x; c.pos.z = at.z;
  c.ry = c.targetRy = p.yaw;
}

// Put everyone where Supabase last saw them. Staff stand there briefly, then the routine walks them back.
export async function restorePositions() {
  const r = await get('office/state.json');
  if (!r.ok) return;
  const { owner, staff: saved = {} } = r.data;
  if (owner) place(me, owner, staff);
  let restoredOfficeSeat = false;
  for (const c of staff) {
    if (c.def.office) {
      c.stop();
      c.level = c.seat.level;
      c.pos.x = c.seat.x; c.pos.z = c.seat.z;
      c.ry = c.targetRy = c.seat.ry;
      c.pose = 'work'; c.state = 'work'; c.afterBreak = null; c.timer = rand(30, 60);
      restoredOfficeSeat = true;
      continue;
    }
    const p = saved[c.def.id];
    if (!p || roomAt(p)?.id === 'subi') continue;
    if (Math.hypot(c.pos.x - p.x, c.pos.z - p.z) <= 0.5) continue; // still at the desk
    place(c, p, [me, ...staff.filter(other => other !== c)]);
    c.pose = 'stand'; c.state = 'break'; c.afterBreak = null; c.timer = rand(4, 8);
  }
  lastSent = restoredOfficeSeat ? '' : JSON.stringify(snapshot());
}

function save({ beacon = false } = {}) {
  const body = JSON.stringify(snapshot());
  if (body === lastSent) return;
  lastSent = body;
  if (beacon && navigator.sendBeacon) navigator.sendBeacon('office/character-state', new Blob([body], { type: 'application/json' }));
  else post('office/character-state', JSON.parse(body), { keepalive: true });
}

export function startPositionSync() {
  setInterval(save, SAVE_EVERY_MS);
  addEventListener('pagehide', () => save({ beacon: true }));
  document.addEventListener('visibilitychange', () => { if (document.hidden) save({ beacon: true }); });
}
