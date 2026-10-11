// Kantor Loker WFH: wires every module together and runs the frame loop
import { renderer, scene, camera, controls, clock, updateLightPool, adaptQuality } from './core/engine.js';
import { animated } from './core/factory.js';
import { store } from './core/store.js';
import { trees } from './world/props.js';
import { clouds } from './world/sky.js';
import { swings } from './world/arena.js';
import { spots } from './world/spots.js';
import './buildings/houses.js';
import { chars } from './characters/char.js';
import { staff, staffMood } from './characters/team.js';
import { me, updateMe } from './characters/player.js';
import { say, updateBubbles } from './fx/bubbles.js';
import { updateParts } from './fx/particles.js';
import { updateStaff } from './ai/routine.js';
import { updatePong } from './ai/pong.js';
import { updateChatter, updateVisits } from './ai/conversation.js';
import { $, toast } from './ui/dom.js';
import './ui/card.js';
import './ui/nav.js';
import './ui/customize.js';
import './ui/hud.js';
import './ui/board.js';
import { updateLiftPanel } from './ui/lift.js';
import { setAuto } from './ui/inbox.js';
import { night, followClock } from './systems/night.js';
import { updateCutaway } from './systems/cutaway.js';
import { updateWorld } from './systems/life.js';
import { updateCamera } from './systems/camera.js';
import { keyMove } from './systems/input.js';
import { initAnimals, updateAnimals } from './world/animals.js';
import { loadStats, poll } from './systems/sync.js';
import { initSettings } from './ui/settings.js';
import { restorePositions, startPositionSync } from './systems/positions.js';
import { loadPrefs } from './systems/prefs.js';
import { applyLook } from './ui/customize.js';
import { applySound } from './ui/hud.js';
import './ui/logs.js';
import './systems/realtime.js';

let frameNo = 0;
function frame() {
  const dt = Math.min(clock.getDelta(), 0.05), t = clock.elapsedTime;
  keyMove(dt);
  for (const f of [...animated]) f(t, dt);
  for (const c of staff) updateStaff(c, dt, t);
  updateMe(dt);
  for (const c of chars) c.update(dt, t);
  updatePong(dt); updateChatter(dt); updateVisits(dt); updateWorld(dt, t);
  updateLightPool(dt, store.fp ? camera.position : controls.target, night);
  if ((frameNo = (frameNo + 1) % 2) === 0 || store.fp) renderer.shadowMap.needsUpdate = true;
  adaptQuality(dt);
  swings.forEach(s => { if (!spots.some(sp => sp.swing === s && sp.by && sp.by.pose === 'swing')) s.rotation.x *= 0.96; });
  clouds.forEach(c => { c.position.x += c.userData.v * dt; if (c.position.x > 110) c.position.x = -110; });
  trees.forEach(tr => tr.rotation.z = Math.sin(t * 0.8 + tr.userData.sway) * 0.02);
  updateAnimals(dt, t);
  updateParts(dt); updateCutaway(); updateLiftPanel(); updateCamera(dt); if (!store.fp) controls.update();
  renderer.render(scene, camera);
  updateBubbles();
  requestAnimationFrame(frame);
}

followClock();
await loadStats();
initSettings();
await restorePositions();
// owner preferences live in Supabase (app_settings ui_*)
const prefs = await loadPrefs();
if (prefs.look) { try { applyLook(JSON.parse(prefs.look)); } catch {} }
applySound(prefs.sound === '1');
startPositionSync();
poll();
if (store.live && prefs.auto !== '0' && !store.S.work?.auto) setAuto(true);
staff.forEach(c => c.setMood(staffMood(c, 0)));
initAnimals();
$('loading').style.opacity = 0; setTimeout(() => $('loading').remove(), 700);
setTimeout(() => $('hint').style.opacity = 0, 12000);
setTimeout(() => { say(me, `Halo! Ini kantor bot lokermu 🏢`); toast(store.live ? '🟢 Terhubung ke data bot' : '🟡 Pakai data contoh'); }, 900);
frame();
