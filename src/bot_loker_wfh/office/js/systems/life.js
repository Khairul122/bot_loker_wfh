// ---------- living world: doors, TVs, windows, chimney smoke, toilet doors, birds, fireflies ----------
import * as THREE from 'three';
import { scene } from '../core/engine.js';
import { pick } from '../core/util.js';
import { stalls } from '../buildings/rooms/kantin.js';
import { houses } from '../buildings/houses.js';
import { inR } from '../world/navigation.js';
import { spots } from '../world/spots.js';
import { water, birds, fireflies, ffBase } from '../world/sky.js';
import { chars } from '../characters/char.js';
import { me, myLook } from '../characters/player.js';
import { say } from '../fx/bubbles.js';
import { toast } from '../ui/dom.js';
import { night } from './night.js';

let meHouse = null;
const smoke = [];
const smokeMat = new THREE.MeshBasicMaterial({ color: 0xe8e8ee, transparent: true, opacity: 0.6, depthWrite: false });
const smokeGeo = new THREE.SphereGeometry(0.22, 8, 6);
export function updateWorld(dt, t) {
  for (const h of houses) {
    const near = chars.some(c => c.level === 0 && Math.abs(c.pos.x - h.x) < 1.3 && Math.abs(c.pos.z - h.front) < 1.5);
    h.door.rotation.y += ((near ? 1.5 : 0) - h.door.rotation.y) * Math.min(1, dt * 6);
    const home = h.who === me ? me.level === 0 && inR(me.pos.x, me.pos.z, h.box, 0) : h.who?.state === 'home';
    h.win.emissiveIntensity += ((night && home ? 1.2 : 0) - h.win.emissiveIntensity) * Math.min(1, dt * 3);
    const tvOn = h.tv.by && h.tv.by.spot === h.tv;
    if (tvOn) h.tvMat.color.setHSL((t * 0.07) % 1, 0.55, 0.42 + Math.sin(t * 9) * 0.07 + (Math.random() < 0.04 ? 0.15 : 0));
    else h.tvMat.color.setHex(0x15151c);
    // a chimney puffs while somebody is at home in the evening
    if (night && (home || h.who?.state === 'sleep') && h.chimney.visible && Math.random() < dt * 1.2) {
      const p = new THREE.Mesh(smokeGeo, smokeMat.clone()); p.position.set(h.x + 1.2, 4.4, h.z - 1); p.userData.life = 3; scene.add(p); smoke.push(p);
    }
  }
  for (let i = smoke.length - 1; i >= 0; i--) {
    const p = smoke[i]; p.userData.life -= dt;
    p.position.y += dt * 0.7; p.position.x += dt * 0.25; p.scale.setScalar(1 + (3 - p.userData.life) * 0.6);
    p.material.opacity = Math.max(0, p.userData.life / 5);
    if (p.userData.life <= 0) { scene.remove(p); p.material.dispose(); smoke.splice(i, 1); }
  }
  for (const s of stalls) { const occ = s.spot.by && s.spot.by.spot === s.spot; s.hinge.rotation.y += ((occ ? 0 : -1.2) - s.hinge.rotation.y) * Math.min(1, dt * 5); }
  for (const s of spots) if (s.plate?.visible && (!s.by || s.by.spot !== s)) s.plate.visible = false;
  // birds circle by day, fireflies drift over the park at night
  birds.forEach((b, i) => {
    const a = t * 0.18 + b.userData.o;
    b.position.set(Math.cos(a) * b.userData.r, 30 + Math.sin(t * 0.5 + i) * 2, Math.sin(a) * b.userData.r - 10);
    b.rotation.y = -a; b.children.forEach((w, k) => w.rotation.x = (k ? 1 : -1) * Math.sin(t * 9 + i) * 0.6);
  });
  if (fireflies.visible) {
    const p = fireflies.geometry.attributes.position;
    for (let i = 0; i < p.count; i++) { const o = ffBase[i]; p.setXYZ(i, o.x + Math.sin(t * 0.7 + i) * 0.8, o.y + Math.sin(t * 1.3 + i * 2) * 0.4, o.z + Math.cos(t * 0.6 + i) * 0.8); }
    p.needsUpdate = true; fireflies.material.opacity = 0.6 + Math.sin(t * 3) * 0.3;
  }
  water.position.y = -0.6 + Math.sin(t * 0.8) * 0.05;
  // greet the owner when walking into somebody's house
  const hNow = me.level === 0 ? houses.find(h => inR(me.pos.x, me.pos.z, h.box, 0)) || null : null;
  if (hNow !== meHouse) {
    meHouse = hNow;
    const o = hNow?.who;
    if (o === me) toast('🏠 Rumahmu · klik kasur untuk tidur, TV untuk nonton, kulkas untuk minum');
    else if (o?.state === 'home') { o.doEmote('wave', 2); say(o, pick([`Eh bos ${myLook.name}! Mampir 😄`, 'Selamat datang di rumahku 🏠', 'Ambil minum di kulkas aja bos 🥤'])); }
    else if (o?.state === 'sleep') say(o, 'Zzz… 💤', 2.5);
    else if (o) toast(`🏠 Rumah ${o.name} · orangnya lagi di kantor`);
  }
}
