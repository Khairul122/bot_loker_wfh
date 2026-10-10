// rooftop garden: planters, string lights, parasol, hammock
import * as THREE from 'three';
import { add, box, cyl, sph, group, sign, walkables } from '../core/factory.js';
import { FH, W, D, ROOF } from '../core/util.js';
import { flowers } from '../world/props.js';

export const roof = group(0, ROOF * FH, 0);
const roofSlab = box(W + 0.8, 0.4, D + 0.8, 0xbfd9a8, 0, -0.2, 0, roof);
walkables.push({ mesh: roofSlab, level: ROOF });
for (const [x, z, w, d] of [[0, -D / 2 - 0.3, W + 0.8, 0.2], [-W / 2 - 0.3, 0, 0.2, D + 0.8], [0, D / 2 + 0.3, W + 0.8, 0.2]]) box(w, 0.9, d, 0xffffff, x, 0.45, z, roof);
for (let k = 0; k < 4; k++) { box(2.6, 0.6, 1, 0xc4895a, -6 + k * 3.4, 0.3, -5, roof); flowers(-6 + k * 3.4, -5, 6, roof); }
for (let k = 0; k < 24; k++) { const x = -9 + k * 0.78; sph(0.1, 0xfff1c9, x, 2.6 + Math.sin(k * 0.8) * 0.25, 0, roof, { glow: 0xffc96b, cast: false }); }
for (const x of [-9.2, 9.2]) cyl(0.05, 0.05, 2.8, 0x5a4a42, x, 1.4, 0, roof);
export const parasol = group(4, 0, 2.5, roof); cyl(0.05, 0.05, 2.4, 0xffffff, 0, 1.2, 0, parasol); add(new THREE.ConeGeometry(1.8, 0.6, 12), 0xef8a6b, 0, 2.5, 0, parasol);
export const hammock = group(-5, 0, 2.5, roof);
for (const x of [-1.6, 1.6]) cyl(0.06, 0.06, 1.6, 0x9a6b4a, x, 0.8, 0, hammock);
box(3, 0.08, 0.9, 0xf2b84b, 0, 0.75, 0, hammock);
sign('🌿', 'Taman Atap', '#6bb38a', '#fff', 0, 1.6, -D / 2 - 0.15, roof, 5);
