// ---------- outdoors west: pond with a fountain and a pier, picnic lawn, coffee cart; garden terrace by the office ----------
import * as THREE from 'three';
import { scene } from '../core/engine.js';
import { add, mat, box, cyl, sph, group, sign, animated } from '../core/factory.js';
import { rand, pick } from '../core/util.js';
import { addSolid } from './navigation.js';
import { tree, flowers, lamp, bench, path, rock, bush } from './props.js';

// ---------- pond: stone rim, lily pads, reeds, a fountain, a pier to watch the ducks from ----------
const PX = -30, PZ = -6;
cyl(5.9, 6, 0.05, 0x9fd28a, PX, 0.015, PZ, scene, { cast: false });
export const pond = cyl(5.5, 5.5, 0.08, 0x7fc8e0, PX, 0.05, PZ, scene, { cast: false });
cyl(3.2, 3.2, 0.02, 0x5fb3d3, PX, 0.1, PZ, scene, { cast: false });
for (let k = 0; k < 18; k++) {
  const a = k / 18 * Math.PI * 2;
  if (Math.abs(Math.atan2(Math.sin(a), Math.cos(a))) < 0.35) continue; // the pier
  rock(PX + Math.cos(a) * 5.7, PZ + Math.sin(a) * 5.7, rand(0.8, 1.2));
}
const pads = [];
for (let k = 0; k < 7; k++) {
  const a = rand(0, 6.28), r = rand(3.4, 4.8), pad = group(PX + Math.cos(a) * r, 0.1, PZ + Math.sin(a) * r);
  cyl(0.45, 0.45, 0.03, 0x6fae6a, 0, 0.02, 0, pad, { cast: false });
  if (k % 2) sph(0.1, 0xf4a7c0, 0.1, 0.08, 0, pad, { cast: false });
  pad.userData.o = rand(0, 6); pads.push(pad);
}
for (let k = 0; k < 14; k++) { const a = Math.PI + rand(-0.6, 0.6), r = rand(4.6, 5.3); cyl(0.025, 0.03, rand(0.8, 1.3), 0x6b8f4e, PX + Math.cos(a) * r, 0.5, PZ + Math.sin(a) * r, scene, { cast: false }); }
cyl(0.7, 0.8, 0.35, 0xc4beb3, PX, 0.17, PZ);
const jet = cyl(0.08, 0.16, 1.4, 0, PX, 0.9, PZ, scene, { material: mat(0xdff4ff, { p: { transparent: true, opacity: 0.7 } }), cast: false });
const spray = sph(0.35, 0, PX, 1.6, PZ, scene, { material: mat(0xdff4ff, { p: { transparent: true, opacity: 0.45 } }), cast: false });
animated.push(t => {
  const u = 1 + Math.sin(t * 3) * 0.12; jet.scale.y = u; jet.position.y = 0.9 * u; spray.position.y = 1.55 * u; spray.scale.setScalar(1 + Math.sin(t * 6) * 0.1);
  for (const p of pads) p.position.y = 0.1 + Math.sin(t * 1.2 + p.userData.o) * 0.015;
});
addSolid([PX - 4, PX + 4, PZ - 4, PZ + 4]); // the water itself; the ducks' spot is on the pier
const pier = group(-24.6, 0, -4, scene);
box(2.8, 0.1, 1.6, 0xb98d63, 0, 0.16, 0, pier);
for (let k = 0; k < 6; k++) box(0.04, 0.02, 1.6, 0x8a6b55, -1.2 + k * 0.48, 0.22, 0, pier, { cast: false });
for (const s of [-1, 1]) { box(2.8, 0.06, 0.06, 0x8a6b55, 0, 0.75, s * 0.78, pier); for (const x of [-1.3, 0, 1.3]) box(0.08, 0.6, 0.08, 0x8a6b55, x, 0.45, s * 0.78, pier); }
for (const [x, z, s] of [[-37, -2, 1], [-36.5, -11, 1.2], [-23.5, -9, 0.9], [-25, 0.6, 0.8]]) bush(x, z, s);

// ---------- paths, flower beds, lamps, trees ----------
path(-29.5, 1.3, 12, 2); path(-28, 6.5, 2, 9.6);
for (const [x, z] of [[-38, 3], [-26, 9.5], [-34, 18], [-27, 22], [-40, -12]]) flowers(x, z);
[[-40, -14, 1.2, 1], [-42, 2, 1], [-38, 13, 1.2, 2], [-35, 22, 1.2, 1], [-25, 18.5, 1], [-44, -4, 1, 1], [40, 16, 1.1], [44, -10, 1, 1],
  [36, 29, 0.9, 2], [28, 22, 1], [35, 32, 1, 1], [-35, -24, 1, 1], [35, -23, 1], [0, -40, 1.1, 2], [-8, -43, 1, 1], [16, -39, 1],
  [-18, 31, 1, 2], [18, 31, 1], [-30, 30, 1, 1]].forEach(([x, z, s, k]) => tree(x, z, s, k || 0));
lamp(-21.5, 12, scene); lamp(-30.2, 6, scene); lamp(21.5, 12, scene); lamp(30, 3, scene); lamp(-4.6, 21.5, scene);
export const benchA = bench(-24, 3, Math.PI), benchB = bench(-36, 6, Math.PI * 0.75), benchC = bench(-22, -14, 0.2);
const totem = group(-22.8, 0, 6.2, scene, Math.PI / 2);
for (const s of [-1, 1]) cyl(0.08, 0.08, 2.6, 0x8a6b55, s * 1.9, 1.3, 0, totem);
box(4, 0.12, 0.12, 0x8a6b55, 0, 2.55, 0, totem);
sign('🌳', 'Taman', '#6bb38a', '#fff', 0, 2.15, 0.05, totem, 3.6);

// ---------- picnic lawn: a checked blanket with a basket, plates and a cake ----------
export const picnic = box(3, 0.03, 3, 0xef8a6b, -30, 0.05, 12, scene, { cast: false });
for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) if ((i + j) % 2) box(1, 0.01, 1, 0xfff2df, -1 + i, 0.02, -1 + j, picnic, { cast: false });
const basket = group(-29, 0, 12.6, scene);
box(0.6, 0.35, 0.4, 0xc4895a, 0, 0.24, 0, basket); const handle = add(new THREE.TorusGeometry(0.22, 0.025, 6, 14, Math.PI), 0x8a6b55, 0, 0.42, 0, basket); handle.rotation.y = Math.PI / 2;
for (const [x, z] of [[-30.8, 12.4], [-29.6, 11.6]]) cyl(0.18, 0.18, 0.02, 0xffffff, x, 0.08, z, scene, { cast: false });
cyl(0.22, 0.22, 0.16, 0xffe0e6, -30.2, 0.14, 12.8, scene); sph(0.05, 0xef4a5a, -30.2, 0.26, 12.8, scene, { cast: false });

// ---------- coffee cart: striped awning, menu board, stools ----------
export const kiosk = group(-34, 0, 0, scene);
box(3.4, 1.05, 1.1, 0x8a5e3e, 0, 0.52, 0, kiosk); box(3.6, 0.08, 1.3, 0xfff2df, 0, 1.08, 0, kiosk);
box(3.2, 0.5, 0.04, 0xc4895a, 0, 0.55, 0.57, kiosk, { cast: false });
for (const x of [-1.6, 1.6]) for (const z of [-0.45, 0.45]) cyl(0.04, 0.04, 1.6, 0xffffff, x, 1.9, z, kiosk);
for (let k = 0; k < 6; k++) { const s = box(0.62, 0.06, 1.7, k % 2 ? 0xffffff : 0xe0574a, -1.55 + k * 0.62, 2.78, 0.15, kiosk); s.rotation.x = 0.22; }
box(0.5, 0.55, 0.45, 0x3b3b48, -1, 1.38, -0.2, kiosk); for (let k = -1; k <= 1; k++) cyl(0.08, 0.07, 0.16, 0xffffff, 0.3 + k * 0.4, 1.2, 0.25, kiosk, { cast: false });
const menu = group(1.95, 0, 0.9, kiosk, -0.3); box(0.05, 1, 0.05, 0x8a6b55, 0, 0.5, 0, menu); box(0.6, 0.7, 0.05, 0x2f3b36, 0, 1.2, 0, menu);
for (const x of [-1.2, -0.2]) { cyl(0.2, 0.2, 0.06, 0xe0574a, x, 0.72, 1.35, kiosk); cyl(0.04, 0.04, 0.7, 0x3f4a5a, x, 0.35, 1.35, kiosk); }
sign('☕', 'Kafe Santai', '#8a6b55', '#fff', 0, 3.25, 0.95, kiosk, 3.2);
addSolid([-35.8, -32.2, -0.6, 0.6]);

// ---------- garden terrace in front of the office: deck, pergola with string lights, hammock, parasol ----------
const deck = group(-10.5, 0, 23.5, scene);
box(9, 0.14, 6, 0xc4955e, 0, 0.07, 0, deck, { cast: false });
for (let k = 0; k < 15; k++) box(0.03, 0.02, 6, 0xa87a4c, -4.2 + k * 0.6, 0.15, 0, deck, { cast: false });
const posts = [[-4.2, -2.7], [4.2, -2.7], [-4.2, 2.7], [4.2, 2.7]];
for (const [x, z] of posts) box(0.16, 2.8, 0.16, 0x6b4a33, x, 1.4, z, deck);
for (const z of [-2.7, 2.7]) box(8.7, 0.14, 0.18, 0x6b4a33, 0, 2.8, z, deck);
for (let k = 0; k < 7; k++) box(0.1, 0.1, 5.8, 0x8a5e3e, -3.6 + k * 1.2, 2.9, 0, deck, { cast: false });
for (let k = 0; k < 18; k++) { const u = k / 17; sph(0.08, pick([0xfff1c9, 0xffd27a]), -4.2 + u * 8.4, 2.6 - Math.sin(u * Math.PI) * 0.35, 0, deck, { glow: 0xffc96b, cast: false }); }
sign('🌿', 'Teras Taman', '#6bb38a', '#fff', 0, 2.45, -2.82, deck, 3.4).rotation.y = Math.PI;
for (const x of [-3.9, 3.9]) { box(0.8, 0.5, 0.8, 0xd9c7b0, x, 0.39, 2.3, deck); bush(x, 2.3, 0.8, deck).position.y = 0.4; }
export const hammock = group(-12.2, 0, 23.6);
for (const x of [-1.6, 1.6]) cyl(0.07, 0.07, 1.7, 0x6b4a33, x, 0.95, 0, hammock);
box(3, 0.08, 0.9, 0xf2b84b, 0, 0.75, 0, hammock); box(3, 0.085, 0.2, 0xffffff, 0, 0.75, 0, hammock, { cast: false });
for (const s of [-1, 1]) { const rope = cyl(0.015, 0.015, 0.6, 0xd9c7b0, s * 1.58, 1.05, 0, hammock, { cast: false }); rope.rotation.z = s * 0.9; }
export const parasol = group(-8, 0, 23.3);
cyl(0.05, 0.05, 2.4, 0xffffff, 0, 1.3, 0, parasol);
add(new THREE.ConeGeometry(1.8, 0.6, 12), 0xef8a6b, 0, 2.6, 0, parasol);
for (let k = 0; k < 6; k++) { const r = add(new THREE.ConeGeometry(1.81, 0.6, 12, 1, true, k * Math.PI / 3, Math.PI / 6), 0xffffff, 0, 2.6, 0, parasol, { cast: false }); r.material = mat(0xffffff, { p: { side: THREE.DoubleSide } }); }
cyl(0.45, 0.45, 0.05, 0xfff2df, 0, 0.72, 0, parasol); cyl(0.05, 0.05, 0.7, 0x3f4a5a, 0, 0.35, 0, parasol);
addSolid([-8.45, -7.55, 22.85, 23.75]);
