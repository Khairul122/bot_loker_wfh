// reusable furniture and garden props; each returns its group so callers can tag or move it
import * as THREE from 'three';
import { scene, light } from '../core/engine.js';
import { add, box, cyl, sph, group } from '../core/factory.js';
import { rand, pick } from '../core/util.js';
import { addSolid } from './navigation.js';

export const screens = []; // desk monitors, brighter at night
export const trees = []; // swayed every frame
const drinkCupBody = new THREE.CylinderGeometry(0.075, 0.055, 0.16, 16);
const drinkCupFill = new THREE.CylinderGeometry(0.064, 0.064, 0.008, 16);
const drinkCupHandle = new THREE.TorusGeometry(0.05, 0.012, 8, 14);

// paved walkway with a darker kerb along its long sides
export function path(x, z, w, d, ry = 0) {
  const p = box(w, 0.06, d, 0xeadcc2, x, 0.03, z, scene, { cast: false }); p.rotation.y = ry;
  const long = w >= d;
  for (const s of [-1, 1]) {
    box(long ? w : 0.14, 0.08, long ? 0.14 : d, 0xc9b48f, 0, 0.01, 0, p, { cast: false }).position.set(long ? 0 : s * (w / 2 - 0.07), 0.01, long ? s * (d / 2 - 0.07) : 0);
  }
  return p;
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
export function drinkCup(fillColor = 0x5a3428) {
  const g = new THREE.Group();
  add(drinkCupBody, 0xf5f0e8, 0, 0, 0, g);
  add(drinkCupFill, fillColor, 0, 0.079, 0, g);
  const handle = add(drinkCupHandle, 0xf5f0e8, 0.08, 0, 0, g);
  handle.rotation.y = Math.PI / 2;
  return g;
}
export function armchair(x, z, ry, p, color = 0x8fae8a) {
  const g = group(x, 0, z, p, ry);
  box(0.9, 0.4, 0.85, color, 0, 0.3, 0.05, g); box(0.9, 0.65, 0.2, color, 0, 0.75, -0.35, g);
  for (const s of [-1, 1]) box(0.16, 0.3, 0.85, color, s * 0.45, 0.6, 0.05, g);
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
// ---------- outdoor props: lamp posts, trees, flower beds, benches, hedges, rocks ----------
export function lamp(x, z, p, h = 3) {
  const g = group(x, 0, z, p);
  cyl(0.18, 0.22, 0.25, 0x3f4a5a, 0, 0.12, 0, g);
  cyl(0.05, 0.07, h, 0x3f4a5a, 0, h / 2, 0, g);
  box(0.5, 0.05, 0.08, 0x3f4a5a, 0.2, h, 0, g, { cast: false });
  box(0.26, 0.32, 0.26, 0x3f4a5a, 0.42, h - 0.12, 0, g, { cast: false });
  box(0.2, 0.24, 0.2, 0xfff1c9, 0.42, h - 0.14, 0, g, { glow: 0xffd27a, cast: false });
  light(0.42, h - 0.3, 0, 0xffc982, 16, 14, g);
  return g;
}
// kind 0 round crown, 1 pine, 2 blossom; the trunk is walked around
export function tree(x, z, s = 1, kind = 0) {
  const g = group(x, 0, z);
  cyl(0.18 * s, 0.3 * s, 2 * s, 0x8a5e3e, 0, s, 0, g);
  if (kind === 1) {
    for (let k = 0; k < 3; k++) add(new THREE.ConeGeometry((1.7 - k * 0.4) * s, 1.8 * s, 9), k % 2 ? 0x5f9e6e : 0x4f8c60, 0, (2.4 + k * 1.05) * s, 0, g);
  } else {
    const [a, b, c] = kind === 2 ? [0xf4a7c0, 0xf9c6d6, 0xee8fae] : [0x74b86a, 0x93cf83, 0x62a35e];
    sph(1.45 * s, a, 0, 2.9 * s, 0, g); sph(1.05 * s, b, 0.75 * s, 3.45 * s, 0.35 * s, g);
    sph(0.95 * s, c, -0.75 * s, 3.2 * s, -0.4 * s, g); sph(0.8 * s, b, 0.1 * s, 3.9 * s, -0.5 * s, g);
  }
  addSolid([x - 0.45 * s, x + 0.45 * s, z - 0.45 * s, z + 0.45 * s]);
  g.userData.sway = rand(0, 6); trees.push(g);
  return g;
}
// a round bed: soil, a ring of leaves and blooms
export function flowers(x, z, n = 8, p = scene) {
  const cols = [0xff9aa2, 0xffd166, 0xc3a6ff, 0xffffff, 0xff8fab, 0xf2b84b];
  cyl(1.35, 1.4, 0.12, 0xc9b48f, x, 0.06, z, p, { cast: false });
  cyl(1.25, 1.25, 0.14, 0x7a5a42, x, 0.08, z, p, { cast: false });
  for (let i = 0; i < n + 4; i++) {
    const a = i / (n + 4) * Math.PI * 2 + rand(-0.2, 0.2), r = i < n ? rand(0.2, 0.9) : 1;
    const fx = x + Math.cos(a) * r, fz = z + Math.sin(a) * r;
    if (i < n) { cyl(0.02, 0.02, 0.4, 0x5a9a55, fx, 0.32, fz, p, { cast: false }); sph(0.12, pick(cols), fx, 0.52, fz, p, { cast: false }); }
    else sph(0.22, 0x6fae6a, fx, 0.22, fz, p, { cast: false }).scale.y = 0.6;
  }
}
// slatted wooden bench on dark steel frames; seat faces local +z
export function bench(x, z, ry) {
  const g = group(x, 0, z, scene, ry);
  for (let k = 0; k < 3; k++) box(2.2, 0.06, 0.17, 0xc4895a, 0, 0.5, -0.2 + k * 0.2, g);
  for (let k = 0; k < 2; k++) box(2.2, 0.14, 0.05, 0xc4895a, 0, 0.72 + k * 0.2, -0.3, g);
  for (const s of [-0.95, 0.95]) { box(0.07, 0.5, 0.55, 0x3f4a5a, s, 0.25, 0, g); box(0.07, 0.5, 0.07, 0x3f4a5a, s, 0.75, -0.32, g); }
  const turned = Math.abs(Math.sin(ry)) > 0.5;
  addSolid([x - (turned ? 0.4 : 1.15), x + (turned ? 0.4 : 1.15), z - (turned ? 1.15 : 0.4), z + (turned ? 1.15 : 0.4)]);
  return g;
}
export function hedge(x, z, w, d, p = scene) {
  const g = group(x, 0, z, p);
  box(w, 0.7, d, 0x5f9e5e, 0, 0.35, 0, g);
  for (let k = 0; k < Math.max(2, Math.round(Math.max(w, d) / 0.8)); k++) {
    const u = (k + 0.5) / Math.max(2, Math.round(Math.max(w, d) / 0.8)) - 0.5;
    sph(0.36, 0x6fae6a, w >= d ? u * w : 0, 0.72, w >= d ? 0 : u * d, g, { cast: false }).scale.y = 0.6;
  }
  addSolid([x - w / 2, x + w / 2, z - d / 2, z + d / 2]);
  return g;
}
export function rock(x, z, s = 1, p = scene) {
  const r = sph(0.5 * s, pick([0xb7b2a8, 0xa49d92, 0xc4beb3]), x, 0.12 * s, z, p);
  r.scale.set(1.2, 0.55, 0.9); r.rotation.y = rand(0, 3);
  return r;
}
export function bush(x, z, s = 1, p = scene) {
  const g = group(x, 0, z, p);
  sph(0.55 * s, 0x6fae6a, 0, 0.4 * s, 0, g); sph(0.4 * s, 0x86c47c, 0.35 * s, 0.5 * s, 0.15 * s, g); sph(0.35 * s, 0x5f9e5e, -0.3 * s, 0.35 * s, -0.1 * s, g);
  return g;
}
