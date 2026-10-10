// ---------- outdoors: arena (basketball, swings, slide, pingpong) ----------
import * as THREE from 'three';
import { scene } from '../core/engine.js';
import { add, box, cyl, sph, group, sign } from '../core/factory.js';
import { flowers } from './props.js';

box(12, 0.05, 10, 0xe9a46f, 28, 0.03, -8, scene, { cast: false }); // court
box(11, 0.06, 0.12, 0xffffff, 28, 0.04, -8, scene, { cast: false });
export const hoop = group(28, 0, -13);
cyl(0.12, 0.12, 3.4, 0x666677, 0, 1.7, -0.4, hoop); box(1.8, 1.1, 0.08, 0xffffff, 0, 3.4, -0.1, hoop);
const rim = add(new THREE.TorusGeometry(0.45, 0.04, 8, 20), 0xef6a3a, 0, 3.0, 0.45, hoop); rim.rotation.x = Math.PI / 2;
export const ball = sph(0.26, 0xf08a3d, 29, 0.26, -6);
export const swingFrame = group(20, 0, 3);
for (const x of [-2.2, 2.2]) for (const z of [-0.7, 0.7]) { const l = cyl(0.07, 0.07, 3.2, 0x7aa6d8, x, 1.55, z * 0.6, swingFrame); l.rotation.x = z > 0 ? -0.2 : 0.2; }
cyl(0.07, 0.07, 4.6, 0x7aa6d8, 0, 3.05, 0, swingFrame).rotation.z = Math.PI / 2;
export const swings = [-1, 1].map(x => {
  const pv = group(x, 3.05, 0, swingFrame);
  for (const sx of [-0.3, 0.3]) cyl(0.015, 0.015, 2.4, 0x555555, sx, -1.2, 0, pv, { cast: false });
  box(0.75, 0.08, 0.4, 0xef8a6b, 0, -2.4, 0, pv);
  pv.userData.amp = 0.1; return pv;
});
export const slide = group(26, 0, 7, scene, -Math.PI / 2);
box(1, 2, 1, 0xf2b84b, 0, 1, -1.2, slide); const sl = box(0.9, 0.08, 3.4, 0x6bb38a, 0, 1, 0.5, slide); sl.rotation.x = 0.55;
export const ping = group(34, 0, 4);
box(2.8, 0.08, 1.5, 0x4c9a6a, 0, 0.78, 0, ping); box(0.04, 0.18, 1.5, 0xffffff, 0, 0.9, 0, ping);
for (const [a, b] of [[-1.2, -0.6], [1.2, -0.6], [-1.2, 0.6], [1.2, 0.6]]) box(0.07, 0.78, 0.07, 0x555555, a, 0.39, b, ping);
export const pball = sph(0.06, 0xffffff, 34, 1.0, 4);
pball.visible = false; // driven by updatePong()
sign('🎮', 'Arena Bermain', '#7aa6d8', '#fff', 22, 3.4, 9.1, scene, 4.4);
flowers(36, 12); flowers(18, -18);
