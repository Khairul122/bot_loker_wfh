// ---------- pointer: hover tooltip + click to walk / talk / use ----------
import * as THREE from 'three';
import { renderer, camera } from '../core/engine.js';
import { clickables, walkables } from '../core/factory.js';
import { store } from '../core/store.js';
import { FH, W, D, pick, clamp } from '../core/util.js';
import { island } from '../world/sky.js';
import { MOODS } from '../characters/body.js';
import { me, myLook } from '../characters/player.js';
import { say } from '../fx/bubbles.js';
import { burst } from '../fx/particles.js';
import { useSpot, goHouse } from '../ai/owner-actions.js';
import { $ } from '../ui/dom.js';
import { startChat, endChat } from '../ui/card.js';

const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
let downAt = null;
export function hitAt(e) {
  mouse.set(e.clientX / innerWidth * 2 - 1, -e.clientY / innerHeight * 2 + 1);
  ray.setFromCamera(mouse, camera);
  const targets = clickables.filter(o => isShown(o)).concat(walkables.filter(w => isShown(w.mesh)).map(w => w.mesh), [island]);
  return ray.intersectObjects(targets, false)[0];
}
function isShown(o) { while (o) { if (!o.visible || o.userData.faded) return false; o = o.parent; } return true; }
renderer.domElement.addEventListener('pointerdown', e => { downAt = [e.clientX, e.clientY]; });
renderer.domElement.addEventListener('pointerup', e => {
  if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 6) return;
  interact(hitAt(e));
});
export function interact(h) {
  if (!h) return;
  const ud = h.object.userData;
  $('custom').classList.remove('show');
  if (ud.kind === 'char' && ud.char !== me) { store.overview = false; startChat(ud.char); return; }
  if (ud.kind === 'char' && ud.char === me) { me.doEmote(pick(['wave', 'dance', 'cheer'])); say(me, MOODS[me.mood].emo + ' ' + MOODS[me.mood].label); return; }
  if (ud.kind === 'spot') { store.overview = false; useSpot(ud.kindName, ud.house); return; }
  if (ud.kind === 'house') { store.overview = false; endChat(); goHouse(ud.house); return; }
  endChat();
  const w = walkables.find(x => x.mesh === h.object);
  const level = w ? w.level : 0;
  let { x, z } = h.point;
  if (level > 0) { x = clamp(x, -W / 2 + 0.6, W / 2 - 0.4); z = clamp(z, -D / 2 + 0.6, D / 2 - 0.4); }
  else if (Math.hypot(x, z) > 46) return;
  store.overview = false;
  me.goTo(level, x, z);
  burst(new THREE.Vector3(x, level * FH - 1.8, z), ['📍'], 1);
}
const TIP = { bench: 'Duduk di bangku', swing: 'Main ayunan', picnic: 'Piknik', pond: 'Lihat bebek', hoop: 'Main basket', ping: 'Main pingpong', slide: 'Main seluncuran', kafe: 'Beli kopi', hammock: 'Rebahan di hammock', parasol: 'Bersantai', kopi: 'Ngopi', sofa: 'Duduk di sofa', lift: 'Naik lift', kantin: 'Pesan makanan', toilet: 'Toilet', wastafel: 'Cuci tangan', kasur: 'Tidur', tv: 'Nonton TV', kulkas: 'Buka kulkas', owner: 'Meja owner · laporan kinerja', rapat: 'Mulai rapat tim' };
renderer.domElement.addEventListener('pointerleave', () => { $('tip').style.display = 'none'; });
let lastHover = 0;
renderer.domElement.addEventListener('pointermove', e => {
  const nowMs = performance.now();
  const looking = store.fp && downAt && e.buttons;
  if (!looking && nowMs - lastHover < 70) return; // raycasting thousands of meshes per mouse event is the main input lag
  lastHover = nowMs;
  if (looking) {
    store.yaw -= e.movementX * 0.005; store.pitch = clamp(store.pitch - e.movementY * 0.004, -1.2, 1.1);
    $('tip').style.display = 'none'; return;
  }
  const h = hitAt(e); const ud = h?.object.userData || {};
  const tip = $('tip');
  if (ud.kind === 'char') { tip.style.display = 'block'; tip.textContent = ud.char === me ? myLook.name : `${ud.char.name} · ${ud.char.def.role}`; }
  else if (ud.kind === 'spot') { tip.style.display = 'block'; tip.textContent = (TIP[ud.kindName] || 'Main') + (ud.house ? ` · rumah ${ud.house.name}` : ''); }
  else if (ud.kind === 'house') { tip.style.display = 'block'; tip.textContent = `🏠 Rumah ${ud.house.name} · masuk`; }
  else tip.style.display = 'none';
  tip.style.left = e.clientX + 14 + 'px'; tip.style.top = e.clientY + 14 + 'px';
  renderer.domElement.style.cursor = ud.kind ? 'pointer' : 'default';
});
