// ---------- living world: doors, unit lights and TVs, mailbox flags, resident board, laundry, toilet doors, birds, fireflies ----------
import { pick } from '../core/util.js';
import { stalls } from '../buildings/rooms/toilet.js';
import { office } from '../buildings/office.js';
import { houses, rusun, drawResidents, updateLaundry, unitAt } from '../buildings/houses.js';
import { spots } from '../world/spots.js';
import { water, birds, fireflies, ffBase } from '../world/sky.js';
import { chars } from '../characters/char.js';
import { me, myLook } from '../characters/player.js';
import { say } from '../fx/bubbles.js';
import { toast } from '../ui/dom.js';
import { night } from './night.js';

let meHouse = null, boardT = 0;
const STATUS = { home: ['🏠 di rumah', '#4f9a7d'], sleep: ['😴 tidur', '#7a6fb0'], commute: ['🚶 pulang', '#d9a23a'] };
const statusOf = h => {
  if (h.who === me) return unitAt(me.pos) === h ? { label: '🏠 di rumah', color: '#4f9a7d' } : { label: '👑 keliling', color: '#c9774e' };
  const [label, color] = STATUS[h.who?.state] || ['💼 di kantor', '#8a9a94'];
  return { label, color };
};
const isHome = h => h.who === me ? unitAt(me.pos) === h : ['home', 'sleep'].includes(h.who?.state);
export function updateWorld(dt, t) {
  for (const d of [...office.doors, ...rusun.doors]) {
    const near = chars.some(c => Math.abs(c.pos.x - d.x) < 1.8 && Math.abs(c.pos.z - d.z) < 1.8);
    const u = d.u + ((near ? 1 : 0) - d.u) * Math.min(1, dt * 6);
    if (Math.abs(u - d.u) > 1e-4) { d.u = u; d.set(u); }
  }
  for (const h of houses) {
    const home = isHome(h);
    h.flag.visible = home;
    h.win.emissiveIntensity += ((night && home ? 1.2 : 0) - h.win.emissiveIntensity) * Math.min(1, dt * 3);
    const tvOn = h.tv.by && h.tv.by.spot === h.tv;
    if (tvOn) h.tvMat.color.setHSL((t * 0.07) % 1, 0.55, 0.42 + Math.sin(t * 9) * 0.07 + (Math.random() < 0.04 ? 0.15 : 0));
    else h.tvMat.color.setHex(0x15151c);
  }
  if ((boardT -= dt) <= 0) { boardT = 2; drawResidents(statusOf); }
  updateLaundry(t);
  for (const s of stalls) { const occ = s.spot.by && s.spot.by.spot === s.spot; s.hinge.rotation.y += ((occ ? s.closed : s.open) - s.hinge.rotation.y) * Math.min(1, dt * 5); }
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
  const hNow = unitAt(me.pos);
  if (hNow !== meHouse) {
    meHouse = hNow;
    const o = hNow?.who;
    if (o === me) toast('🏠 Unitmu · klik kasur untuk tidur, TV untuk nonton, kulkas untuk minum');
    else if (o?.state === 'home') { o.doEmote('wave', 2); say(o, pick([`Eh bos ${myLook.name}! Mampir 😄`, 'Selamat datang di unitku 🏠', 'Ambil minum di kulkas aja bos 🥤'])); }
    else if (o?.state === 'sleep') say(o, 'Zzz… 💤', 2.5);
    else if (o) toast(`🏠 Unit ${o.name} · orangnya lagi di kantor`);
  }
}
