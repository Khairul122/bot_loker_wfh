// reusable furniture and garden props; each returns its group so callers can tag or move it
import * as THREE from 'three';
import { scene, light } from '../core/engine.js';
import { add, box, cyl, sph, group } from '../core/factory.js';
import { rand, pick } from '../core/util.js';

export const screens = []; // desk monitors, brighter at night
export const trees = []; // swayed every frame

export function path(x, z, w, d, ry = 0) {
  const p = box(w, 0.06, d, 0xf1dcb5, x, 0.03, z, scene, { cast: false }); p.rotation.y = ry; return p;
}
export function plant(x, z, p, s = 1) {
  const g = group(x, 0, z, p);
  cyl(0.28 * s, 0.22 * s, 0.45 * s, 0xd98b5f, 0, 0.22 * s, 0, g);
  sph(0.45 * s, 0x6fae6a, 0, 0.75 * s, 0, g); sph(0.32 * s, 0x86c47c, 0.2 * s, 1.0 * s, 0.1 * s, g);
  return g;
}
export function chair(x, z, ry, p, color = 0x7a8fb8) {
  const g = group(x, 0, z, p, ry);
  box(0.55, 0.08, 0.55, color, 0, 0.48, 0, g); box(0.55, 0.6, 0.08, color, 0, 0.8, -0.26, g);
  cyl(0.04, 0.04, 0.44, 0x555555, 0, 0.24, 0, g); cyl(0.25, 0.25, 0.04, 0x555555, 0, 0.02, 0, g);
  return g;
}
export function desk(x, z, ry, p, screen = 0x8fd0ff, chairColor) {
  const g = group(x, 0, z, p, ry);
  box(1.8, 0.08, 0.9, 0xe6c49a, 0, 0.75, 0, g);
  for (const [a, b] of [[-0.8, -0.38], [0.8, -0.38], [-0.8, 0.38], [0.8, 0.38]]) box(0.07, 0.75, 0.07, 0xb98d63, a, 0.37, b, g);
  box(0.9, 0.55, 0.06, 0x3b3b48, 0, 1.12, -0.25, g);
  const s = box(0.8, 0.45, 0.02, screen, 0, 1.12, -0.215, g, { glow: screen, unique: true, cast: false });
  screens.push(s);
  box(0.12, 0.25, 0.08, 0x3b3b48, 0, 0.88, -0.27, g);
  box(0.6, 0.03, 0.2, 0xf4f0ea, 0, 0.8, 0.12, g);
  sph(0.07, 0xffffff, 0.6, 0.86, 0.1, g); // mug
  chair(0, 0.75, Math.PI, g, chairColor);
  // seat position in world space computed by caller
  return g;
}
export function sofa(x, z, ry, p, color = 0xe9967a) {
  const g = group(x, 0, z, p, ry);
  box(2.4, 0.45, 0.9, color, 0, 0.32, 0, g); box(2.4, 0.6, 0.25, color, 0, 0.75, -0.35, g);
  box(0.25, 0.4, 0.9, color, -1.2, 0.6, 0, g); box(0.25, 0.4, 0.9, color, 1.2, 0.6, 0, g);
  return g;
}
export function shelf(x, z, ry, p) {
  const g = group(x, 0, z, p, ry);
  box(2, 2.4, 0.5, 0xc89a6c, 0, 1.2, 0, g);
  const cols = [0xef8a6b, 0x6bb38a, 0x7aa6d8, 0xf2b84b, 0xb48ad8];
  for (let r = 0; r < 3; r++) for (let i = 0; i < 6; i++) box(0.2, 0.5, 0.35, pick(cols), -0.75 + i * 0.3, 0.45 + r * 0.75, 0.1, g);
  return g;
}
export function rug(x, z, r, color, p) { return cyl(r, r, 0.04, color, x, 0.03, z, p, { cast: false }); }
export function lamp(x, z, p, h = 3) {
  const g = group(x, 0, z, p);
  cyl(0.06, 0.08, h, 0x5a4a42, 0, h / 2, 0, g);
  sph(0.28, 0xfff1c9, 0, h + 0.1, 0, g, { glow: 0xffd27a });
  light(0, h - 0.2, 0, 0xffc982, 16, 14, g);
  return g;
}
export function tree(x, z, s = 1, kind = 0) {
  const g = group(x, 0, z);
  cyl(0.22 * s, 0.32 * s, 2 * s, 0x9a6b4a, 0, s, 0, g);
  if (kind) { add(new THREE.ConeGeometry(1.6 * s, 3.4 * s, 10), 0x5f9e6e, 0, 3.4 * s, 0, g); }
  else { sph(1.5 * s, 0x7cbf72, 0, 2.9 * s, 0, g); sph(1.1 * s, 0x93cf83, 0.8 * s, 3.4 * s, 0.3 * s, g); sph(1 * s, 0x6fb06a, -0.7 * s, 3.2 * s, -0.4 * s, g); }
  g.userData.sway = rand(0, 6); trees.push(g);
  return g;
}
export function flowers(x, z, n = 8, p = scene) {
  const cols = [0xff9aa2, 0xffd166, 0xc3a6ff, 0xffffff, 0xff8fab];
  for (let i = 0; i < n; i++) {
    const fx = x + rand(-1.2, 1.2), fz = z + rand(-1.2, 1.2);
    cyl(0.02, 0.02, 0.35, 0x5a9a55, fx, 0.17, fz, p, { cast: false });
    sph(0.11, pick(cols), fx, 0.38, fz, p, { cast: false });
  }
}
export function bench(x, z, ry) {
  const g = group(x, 0, z, scene, ry);
  box(2.2, 0.1, 0.6, 0xc4895a, 0, 0.5, 0, g); box(2.2, 0.5, 0.08, 0xc4895a, 0, 0.85, -0.27, g);
  box(0.1, 0.5, 0.5, 0x5a4a42, -0.9, 0.25, 0, g); box(0.1, 0.5, 0.5, 0x5a4a42, 0.9, 0.25, 0, g);
  return g;
}
