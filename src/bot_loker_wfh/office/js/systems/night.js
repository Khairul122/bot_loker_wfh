// ---------- day / night: follows the real clock until the owner flips it by hand ----------
import { scene, hemi, sun, lightPool, resetLights } from '../core/engine.js';
import { glow } from '../core/factory.js';
import { screens } from '../world/props.js';
import { stars, water, fireflies, birds, moon } from '../world/sky.js';
import { $ } from '../ui/dom.js';

export let night = false;
let nightManual = false;
export function setNight(v) {
  night = v; document.body.classList.toggle('night', v); $('bNight').textContent = v ? '☀️' : '🌙';
  const sky = v ? 0x2b2d52 : 0xcfe9f5;
  scene.background.set(sky); scene.fog.color.set(sky);
  hemi.intensity = v ? 0.55 : 1.5; hemi.color.set(v ? 0x8a8fd8 : 0xfff4e0);
  sun.intensity = v ? 0.35 : 2.3; sun.color.set(v ? 0x9fb0ff : 0xffe2b8);
  glow.forEach(m => m.emissiveIntensity = v ? 1 : 0.15);
  screens.forEach(s => s.material.emissiveIntensity = v ? 0.9 : 0.35);
  stars.visible = v; water.material.color.set(v ? 0x3e5c86 : 0x8fd3e8);
  lightPool.forEach(l => l.visible = v); resetLights();
  fireflies.visible = v; birds.forEach(b => b.visible = !v);
  moon.visible = v;
}
$('bNight').onclick = () => { nightManual = true; setNight(!night); };

const clockNight = () => { const h = new Date().getHours(); return h >= 18 || h < 6; };
export function followClock() {
  setNight(clockNight());
  setInterval(() => { if (!nightManual && clockNight() !== night) setNight(clockNight()); }, 60000);
}
