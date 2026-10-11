// ---------- outdoors: park, pond with ducks, cafe kiosk ----------
import { scene } from '../core/engine.js';
import { box, cyl, sph, group, sign, animated } from '../core/factory.js';
import { rand } from '../core/util.js';
import { tree, flowers, lamp, bench } from './props.js';

export const pond = cyl(6, 6, 0.08, 0x7fc8e0, -30, 0.05, -6, scene, { cast: false });
cyl(6.4, 6.4, 0.06, 0xd9c7a4, -30, 0.02, -6, scene, { cast: false });
for (let k = 0; k < 5; k++) cyl(0.5, 0.5, 0.05, 0x7cbf72, -30 + rand(-4, 4), 0.11, -6 + rand(-4, 4), scene, { cast: false });
// Ducks are procedurally managed and rendered in animals.js
// the strip behind the office (z < -15) is the housing estate, keep trees off it
[[-38, -14, 1.2, 1], [-40, 2, 1], [-36, 14, 1.2], [-18, 18, 0.9, 1], [-26, 20, 1], [-44, -4, 1, 1], [40, 16, 1.1], [44, -10, 1, 1], [12, 24, 0.9], [-8, 26, 1], [30, 24, 1, 1], [-35, -24, 1, 1], [35, -23, 1], [0, -40, 1.1], [-6, -47, 1, 1], [16, -39, 1]].forEach(([x, z, s, k]) => tree(x, z, s, k || 0));
flowers(-24, -2); flowers(-36, 2); flowers(-20, 14); flowers(-12, 18); flowers(8, 18); flowers(14, 16); flowers(-4, -18);
lamp(-17, 12, scene); lamp(-30, 6, scene); lamp(17, 12, scene); lamp(30, 3, scene); lamp(-6, 16, scene);
export const benchA = bench(-24, 3, Math.PI), benchB = bench(-36, 6, Math.PI * 0.75), benchC = bench(-22, -14, 0.2);
export const picnic = box(3, 0.04, 3, 0xef8a6b, -30, 0.05, 12, scene, { cast: false });
box(0.6, 0.4, 0.4, 0xc4895a, -29, 0.25, 12.5); // picnic basket
sign('🌳', 'Taman', '#6bb38a', '#fff', -22, 3.4, 9.1, scene, 4);

// cafe kiosk
export const kiosk = group(-12, 0, 16, scene);
box(3.6, 1.1, 1.4, 0xc4895a, 0, 0.55, 0, kiosk); box(3.8, 0.1, 1.6, 0xfff2df, 0, 1.15, 0, kiosk);
for (const x of [-1.7, 1.7]) cyl(0.06, 0.06, 1.9, 0xffffff, x, 2.1, 0.6, kiosk);
const awning = box(4.2, 0.12, 2, 0xef8a6b, 0, 3, 0.2, kiosk); awning.rotation.x = 0.2;
for (let k = -1; k <= 1; k++) cyl(0.12, 0.1, 0.25, 0xffffff, k * 0.6, 1.33, 0.2, kiosk);
sign('☕', 'Kafe Santai', '#8a6b55', '#fff', 0, 3.6, 0.6, kiosk, 3.4);
