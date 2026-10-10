// ---------- character coordinates: saved to Supabase (via the office server) and restored on load ----------
import { FH, rand } from '../core/util.js';
import { me } from '../characters/player.js';
import { staff } from '../characters/team.js';
import { get } from '../ui/dom.js';

const SAVE_EVERY_MS = 2000;
const r2 = n => Math.round(n * 100) / 100;
let lastSent = '';

function snapshot() {
  const at = c => ({ x: r2(c.pos.x), y: r2(c.level * FH), z: r2(c.pos.z), yaw: r2(c.ry || 0) });
  const state = { owner: at(me), staff: {} };
  for (const c of staff) state.staff[c.def.id] = at(c);
  return state;
}

function place(c, p) {
  c.level = Math.max(0, Math.round(p.y / FH));
  c.y = c.level * FH;
  c.pos.x = p.x; c.pos.z = p.z;
  c.ry = c.targetRy = p.yaw;
}

// Put everyone where Supabase last saw them. Staff stand there briefly, then the routine walks them back.
export async function restorePositions() {
  const r = await get('office/state.json');
  if (!r.ok) return;
  const { owner, staff: saved = {} } = r.data;
  if (owner) place(me, owner);
  for (const c of staff) {
    const p = saved[c.def.id];
    if (!p) continue;
    const away = c.level !== Math.round(p.y / FH) || Math.hypot(c.pos.x - p.x, c.pos.z - p.z) > 0.5;
    place(c, p);
    if (away) { c.inside = null; c.pose = 'stand'; c.state = 'break'; c.afterBreak = null; c.timer = rand(4, 8); }
  }
  lastSent = JSON.stringify(snapshot());
}

function save({ beacon = false } = {}) {
  if (staff.some(c => c.ride) || me.ride) return; // mid-lift: y is in between floors
  const body = JSON.stringify(snapshot());
  if (body === lastSent) return;
  lastSent = body;
  if (beacon && navigator.sendBeacon) navigator.sendBeacon('office/character-state', new Blob([body], { type: 'application/json' }));
  else fetch('office/character-state', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }).catch(() => {});
}

export function startPositionSync() {
  setInterval(save, SAVE_EVERY_MS);
  addEventListener('pagehide', () => save({ beacon: true }));
  document.addEventListener('visibilitychange', () => { if (document.hidden) save({ beacon: true }); });
}
