// ---------- keyboard: WASD walking, lift E/Q, V for POV, Escape closes everything ----------
import * as THREE from 'three';
import { camera } from '../core/engine.js';
import { store } from '../core/store.js';
import { V, ROOF, DOOR_X, clamp } from '../core/util.js';
import { blocked, inLift } from '../world/navigation.js';
import { me } from '../characters/player.js';
import { $ } from '../ui/dom.js';
import { endChat } from '../ui/card.js';
import { togglePerf } from '../ui/perf.js';
import { toggleInbox } from '../ui/inbox.js';
import { toggleResults } from '../ui/results.js';
import { toggleBoard } from '../ui/board.js';
import { toggleReports } from '../ui/reports.js';
import { closeMenu } from '../ui/menu.js';
import { toggleSettings } from '../ui/settings.js';
import { toggleLogs } from '../ui/logs.js';
import { toggleMeeting } from '../ui/meeting.js';
import { setFP } from './camera.js';
import { hitAt, interact } from './pointer.js';

const keys = {};
addEventListener('keydown', e => {
  if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName) || e.ctrlKey || e.metaKey || e.altKey) return;
  keys[e.key.toLowerCase()] = true;
});
addEventListener('keyup', e => { keys[e.key.toLowerCase()] = false; });
// a key released while the window had no focus never sends keyup: forget everything held
const releaseKeys = () => { for (const k in keys) keys[k] = false; };
addEventListener('blur', releaseKeys);
document.addEventListener('visibilitychange', () => { if (document.hidden) releaseKeys(); });
export function keyMove(dt) {
  let x = 0, z = 0;
  if (keys.w || keys.arrowup) z -= 1; if (keys.s || keys.arrowdown) z += 1;
  if (keys.a || keys.arrowleft) x -= 1; if (keys.d || keys.arrowright) x += 1;
  if (!x && !z) return;
  if (me.path.length && me.path[0].ride !== undefined) return;
  me.stop(); endChat();
  const fwd = new THREE.Vector3(); camera.getWorldDirection(fwd); fwd.y = 0; fwd.normalize();
  const right = new THREE.Vector3(-fwd.z, 0, fwd.x);
  const mv = fwd.multiplyScalar(-z).add(right.multiplyScalar(x)).normalize();
  const step = me.speed * dt * (me.energy < 15 ? 0.7 : 1);
  const nx = me.pos.x + mv.x * step, nz = me.pos.z + mv.z * step;
  if (!blocked(me.level, me.pos, nx, nz)) { me.pos.x = nx; me.pos.z = nz; }
  me.targetRy = Math.atan2(mv.x, mv.z); me.kbWalk = true;
}
addEventListener('keydown', e => {
  if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
  const k = e.key.toLowerCase();
  if (k === 'escape') { endChat(); togglePerf(false); toggleInbox(false); toggleResults(false); toggleBoard(false); toggleReports(false); closeMenu(); toggleSettings(false); toggleLogs(false); toggleMeeting(false); $('custom').classList.remove('show'); }
  if (k === 'v') setFP(!store.fp);
  if ((k === 'e' || k === 'q') && inLift(me.pos) && !me.ride) {
    const to = clamp(me.level + (k === 'e' ? 1 : -1), 0, ROOF);
    if (to !== me.level) { me.stop(); me.path = [{ ride: to }, { p: V(DOOR_X, 0) }]; }
  } else if (k === 'e' && store.fp) {
    interact(hitAt({ clientX: innerWidth / 2, clientY: innerHeight / 2 }));
  }
});
