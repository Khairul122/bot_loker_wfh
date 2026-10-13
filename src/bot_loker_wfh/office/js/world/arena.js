// ---------- outdoors east: basketball half court, playground (swings, slide), pingpong table ----------
import * as THREE from 'three';
import { scene } from '../core/engine.js';
import { add, mat, box, cyl, sph, group, sign } from '../core/factory.js';
import { addSolid } from './navigation.js';
import { flowers, bench } from './props.js';

// ---------- half court: painted key, arcs and lines; the rim sits at (29, 3, -12.55) ----------
const CX = 29, CZ = -8;
box(11, 0.05, 10, 0x3f7f9a, CX, 0.03, CZ, scene, { cast: false });
box(4, 0.01, 5.8, 0xe9a46f, CX, 0.06, -10.1, scene, { cast: false });
const line = (w, d, x, z) => box(w, 0.012, d, 0xffffff, x, 0.065, z, scene, { cast: false });
line(11, 0.08, CX, -13); line(11, 0.08, CX, -3); line(0.08, 10, CX - 5.5, CZ); line(0.08, 10, CX + 5.5, CZ);
line(0.08, 5.8, CX - 2, -10.1); line(0.08, 5.8, CX + 2, -10.1); line(4, 0.08, CX, -7.2);
const flatRing = (r, x, z, arc = Math.PI * 2, rot = 0) => { const m = add(new THREE.TorusGeometry(r, 0.04, 4, 48, arc), 0xffffff, x, 0.07, z, scene, { cast: false }); m.rotation.set(-Math.PI / 2, 0, rot); return m; };
flatRing(1.8, CX, -7.2); flatRing(4.6, CX, -12.55, Math.PI, Math.PI);
export const hoop = group(CX, 0, -13);
cyl(0.12, 0.14, 3.6, 0x3f4a5a, 0, 1.8, -0.9, hoop); box(0.1, 0.1, 0.9, 0x3f4a5a, 0, 3.5, -0.45, hoop);
box(1.8, 1.1, 0.08, 0xffffff, 0, 3.45, -0.05, hoop); box(0.6, 0.45, 0.085, 0xef6a3a, 0, 3.25, -0.05, hoop, { cast: false });
const rim = add(new THREE.TorusGeometry(0.45, 0.04, 8, 20), 0xef6a3a, 0, 3.0, 0.45, hoop); rim.rotation.x = Math.PI / 2;
const net = add(new THREE.CylinderGeometry(0.44, 0.28, 0.5, 12, 2, true), 0, 0, 2.74, 0.45, hoop, { cast: false });
net.material = mat(0xffffff, { p: { wireframe: true } });
addSolid([CX - 0.25, CX + 0.25, -14.15, -13.65]);
export const ball = sph(0.26, 0xf08a3d, 30, 0.26, -6);
// bleachers along the east side
const stands = group(36.2, 0, CZ, scene, -Math.PI / 2);
for (let k = 0; k < 3; k++) { box(6, 0.4 * (k + 1), 0.6, 0x9aa3ad, 0, 0.2 * (k + 1), -k * 0.6, stands); box(6, 0.06, 0.6, k % 2 ? 0x5b9bd5 : 0xef8a6b, 0, 0.4 * (k + 1) + 0.03, -k * 0.6, stands, { cast: false }); }
addSolid([35.6, 37.6, CZ - 3, CZ + 3]);

// ---------- playground on a soft mat ----------
box(7.5, 0.03, 7.3, 0x7fc4a8, 25.8, 0.025, 5.6, scene, { cast: false });
export const swingFrame = group(24.5, 0, 3);
for (const x of [-2.3, 2.3]) for (const s of [-1, 1]) { const l = cyl(0.07, 0.07, 3.3, 0xef8a6b, x, 1.55, s * 0.55, swingFrame); l.rotation.x = s * -0.32; }
cyl(0.08, 0.08, 4.9, 0xef8a6b, 0, 3.08, 0, swingFrame).rotation.z = Math.PI / 2;
export const swings = [-1, 1].map((x, k) => {
  const pv = group(x, 3.05, 0, swingFrame);
  for (const sx of [-0.3, 0.3]) cyl(0.015, 0.015, 2.4, 0x555555, sx, -1.2, 0, pv, { cast: false });
  box(0.75, 0.08, 0.4, k ? 0x5b9bd5 : 0xf2b84b, 0, -2.4, 0, pv);
  pv.userData.amp = 0.1; return pv;
});
// tower with a roof and ladder; the chute ends where the slide spot is (24.2, 7)
export const slide = group(26, 0, 7, scene, -Math.PI / 2);
for (const [x, z] of [[-0.6, -1.8], [0.6, -1.8], [-0.6, -0.6], [0.6, -0.6]]) box(0.1, 2.6, 0.1, 0x5b9bd5, x, 1.3, z, slide);
box(1.3, 0.1, 1.3, 0xf2b84b, 0, 1.6, -1.2, slide);
const top = add(new THREE.ConeGeometry(1.05, 0.7, 4), 0xef6a3a, 0, 2.95, -1.2, slide); top.rotation.y = Math.PI / 4;
for (let k = 0; k < 5; k++) box(0.9, 0.05, 0.05, 0xffffff, 0, 0.3 + k * 0.3, -2.25, slide);
for (const s of [-1, 1]) box(0.05, 1.7, 0.05, 0xffffff, s * 0.45, 0.85, -2.25, slide);
const chute = group(0, 1.6, -0.6, slide); chute.rotation.x = 0.46;
box(0.9, 0.06, 3.4, 0x6bb38a, 0, 0, 1.7, chute); for (const s of [-1, 1]) box(0.06, 0.25, 3.4, 0x4c9a6a, s * 0.45, 0.12, 1.7, chute);
addSolid([23.4, 28.4, 6.3, 7.7]);
bench(30.8, 9.4, Math.PI);

// ---------- pingpong: tournament-blue table with lines and a net ----------
export const ping = group(34, 0, 4);
box(2.74, 0.06, 1.52, 0x2e5d9a, 0, 0.76, 0, ping);
for (const [w, d, x, z] of [[2.74, 0.03, 0, -0.745], [2.74, 0.03, 0, 0.745], [0.03, 1.52, -1.355, 0], [0.03, 1.52, 1.355, 0], [2.74, 0.02, 0, 0]]) box(w, 0.005, d, 0xffffff, x, 0.793, z, ping, { cast: false });
box(0.03, 0.16, 1.66, 0xf4f7fa, 0, 0.87, 0, ping, { cast: false });
for (const z of [-0.83, 0.83]) box(0.04, 0.2, 0.04, 0x3f4a5a, 0, 0.86, z, ping, { cast: false });
for (const [a, b] of [[-1.15, -0.6], [1.15, -0.6], [-1.15, 0.6], [1.15, 0.6]]) box(0.08, 0.74, 0.08, 0x3f4a5a, a, 0.37, b, ping);
for (const x of [-0.9, 0.9]) { cyl(0.09, 0.09, 0.02, 0xd8434a, x, 0.8, 0.45, ping, { cast: false }); }
addSolid([32.63, 35.37, 3.24, 4.76]);
export const pball = sph(0.06, 0xffffff, 34, 1.0, 4);
pball.visible = false; // driven by updatePong()

const gate = group(31.5, 0, 10.6, scene);
for (const s of [-1, 1]) cyl(0.08, 0.08, 2.8, 0x3f4a5a, s * 2.3, 1.4, 0, gate);
box(4.8, 0.12, 0.12, 0x3f4a5a, 0, 2.75, 0, gate);
sign('🎮', 'Arena Bermain', '#5b9bd5', '#fff', 0, 2.3, 0.05, gate, 4.2);
flowers(36, 12); flowers(37, -16);
