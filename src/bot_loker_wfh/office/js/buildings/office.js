// The office: one storey, every room behind a real door, furnished room by room.
// Walls drop to waist height and the roof lifts while the owner looks in from above (systems/cutaway.js).
import * as THREE from 'three';
import { scene, light } from '../core/engine.js';
import { add, mat, box, cyl, sph, group, sign, walkables } from '../core/factory.js';
import { OFFICE, ROOMS, DOORS, PODS, WALL_LINES, wallPieces } from '../domain/office-plan.js';
import { addWall } from '../world/navigation.js';
import { path, plant } from '../world/props.js';
import { DIVS } from './divisions.js';
import { solid, cutaway } from './registry.js';
import cari from './rooms/cari.js';
import seleksi from './rooms/seleksi.js';
import tulis from './rooms/tulis.js';
import lamar from './rooms/lamar.js';
import pantau from './rooms/pantau.js';
import freelance from './rooms/freelance.js';
import owner from './rooms/owner.js';
import rapat from './rooms/rapat.js';
import toilet from './rooms/toilet.js';
import fokus from './rooms/fokus.js';
import kantin from './rooms/kantin.js';
import lobi from './rooms/lobi.js';
import santai from './rooms/santai.js';

const { minX, maxX, minZ, maxZ, height: H, wall: T } = OFFICE;
const CX = (minX + maxX) / 2, CZ = (minZ + maxZ) / 2;
const C = { outer: 0xf4ece2, inner: 0xfbf7f1, trim: 0x3f4a5a, frame: 0x55606e, wood: 0x9a6b4a, slab: 0xd6cfc6 };
const glass = mat(0xbfe3f2, { p: { transparent: true, opacity: 0.28, depthWrite: false } });
const paneGlow = { glow: 0xffd89a, cast: false };

// cut: shrinks to waist height in the cutaway; upper: hidden in it; roof: the whole roof group
export const office = { cut: cutaway.cut, upper: cutaway.upper, doors: [], roof: null, cutScale: 0.35 };
const root = group(0, 0, 0, scene);
root.userData.buildingId = 'office';
const upperRoot = group(0, 0, 0, root); office.upper.push(upperRoot);

// A box spanning heights y0..y1 whose origin sits on the floor, so scaling y shrinks it in place.
function piece(w, y0, y1, d, color, x, z, parent, o = {}) {
  const geo = new THREE.BoxGeometry(w, y1 - y0, d); geo.translate(0, (y0 + y1) / 2, 0);
  return add(geo, color, x, 0, z, parent, o);
}
const shrinking = (w, y0, y1, d, color, x, z, o) => { const m = piece(w, y0, y1, d, color, x, z, root, o); office.cut.push(m); return m; };

// ---------- floor ----------
const slab = box(maxX - minX + 0.6, 0.4, maxZ - minZ + 0.6, C.slab, CX, -0.18, CZ, root);
walkables.push({ mesh: slab, level: 0 });
const FLOORS = { owner: 0xc9a27a, meeting: 0xcfd8e6, toilet: 0xe3f1f4, focus: 0xd5e3cf, work: 0xe2e6ea, kantin: 0xf1dcc4, lobby: 0xf3ede4, lounge: 0xf2dcc8 };
for (const r of Object.values(ROOMS)) {
  box(r.x1 - r.x0 - T, 0.02, r.z1 - r.z0 - T, FLOORS[r.id], (r.x0 + r.x1) / 2, 0.03, (r.z0 + r.z1) / 2, root, { cast: false });
}

// ---------- walls ----------
// where interior walls meet an outer wall: no window there, a mullion on the glass facade
const junctions = WALL_LINES.filter(l => l.kind === 'interior' || l.kind === 'glass').flatMap(l => [[l.x0, l.z0], [l.x1, l.z1]]);
const nearJunction = (piece, along) => junctions.some(([x, z]) => piece.alongX
  ? Math.abs(z - piece.rect[2] - T / 2) < 0.01 && Math.abs(x - along) < 1.3
  : Math.abs(x - piece.rect[0] - T / 2) < 0.01 && Math.abs(z - along) < 1.3);

function outerWall(p, w, d, x, z, len) {
  shrinking(w, 0, H, d, C.outer, x, z);
  piece(w + 0.02, H - 0.28, H + 0.02, d + 0.04, C.trim, x, z, upperRoot, { cast: false });
  const n = Math.floor(len / 3.2);
  for (let k = 0; k < n; k++) {
    const along = (p.alongX ? p.rect[0] : p.rect[2]) + (k + 0.5) * (len / n);
    if (nearJunction(p, along)) continue;
    const [wx, wz] = p.alongX ? [along, z] : [x, along];
    box(p.alongX ? 1.9 : T + 0.06, 1.35, p.alongX ? T + 0.06 : 1.9, 0xbfe3f2, wx, 1.75, wz, upperRoot, paneGlow);
    box(p.alongX ? 2.1 : T + 0.12, 0.08, p.alongX ? T + 0.12 : 2.1, C.trim, wx, 1.04, wz, upperRoot, { cast: false });
  }
}
function glassWall(p, w, d, x, z, len, base, top) {
  shrinking(w, 0, base, d, p.kind === 'facade' ? C.outer : C.frame, x, z);
  shrinking(p.alongX ? w : 0.06, base, top, p.alongX ? 0.06 : d, 0, x, z, { material: glass, cast: false });
  const step = 1.6, n = Math.max(1, Math.round(len / step));
  for (let k = 0; k <= n; k++) {
    const along = (p.alongX ? p.rect[0] : p.rect[2]) + k * (len / n);
    const [mx, mz] = p.alongX ? [along, z] : [x, along];
    shrinking(p.alongX ? 0.08 : d, base, top, p.alongX ? d : 0.08, C.frame, mx, mz, { cast: false });
  }
  piece(w, top - 0.1, top, d + 0.02, C.frame, x, z, upperRoot, { cast: false });
}

for (const p of wallPieces()) {
  const [x0, x1, z0, z1] = p.rect, w = x1 - x0, d = z1 - z0, x = (x0 + x1) / 2, z = (z0 + z1) / 2;
  const len = p.alongX ? w : d;
  if (p.door) { doorway(p.door, p.kind); continue; }
  addWall(p.rect);
  if (p.kind === 'exterior') outerWall(p, w, d, x, z, len);
  else if (p.kind === 'facade') glassWall(p, w, d, x, z, len, 0.55, H);
  else if (p.kind === 'glass') glassWall(p, w, d, x, z, len, 0.9, H - 0.02);
  else shrinking(w, 0, H - 0.02, d, C.inner, x, z);
}

// ---------- doors: frame, leaf (hinged or sliding) that opens for anyone close by ----------
function doorway(d, kind) {
  const w = d.width, ry = d.axis === 'x' ? 0 : -Math.PI / 2;
  const inside = Object.values(ROOMS).find(r => d.to.includes(r.id) && (d.to.includes('out') || r.id !== 'work'));
  // the room's side of the door in the door's own frame (local +x runs along the wall)
  const rx = (inside.x0 + inside.x1) / 2 - d.x, rz = (inside.z0 + inside.z1) / 2 - d.z;
  const roomSide = Math.sign(d.axis === 'x' ? rz : -rx) || 1;
  const frame = group(d.x, 0, d.z, root, ry); office.cut.push(frame);
  const head = group(d.x, 0, d.z, upperRoot, ry);
  const flat = group(d.x, 0, d.z, root, ry);
  const outer = kind === 'exterior' || kind === 'facade';
  for (const s of [-1, 1]) box(0.12, 2.4, T + 0.06, C.frame, s * (w / 2 - 0.06), 1.2, 0, frame);
  piece(w, 2.4, H - (outer ? 0 : 0.02), T, outer ? C.outer : C.inner, 0, 0, head);
  box(w, 0.12, T + 0.06, C.frame, 0, 2.4, 0, head, { cast: false });
  box(w, 0.02, T + 0.2, 0xb9ae9f, 0, 0.035, 0, flat, { cast: false }); // threshold
  box(w * 0.75, 0.02, 0.7, d.to.includes('out') ? 0x8a6b55 : 0x6b7b8f, 0, 0.04, -roomSide * 0.75, flat, { cast: false }); // doormat outside the room
  if (!d.to.includes('out')) sign(inside.icon, inside.name, '#3f4a5a', '#fff', 0, 2.78, -roomSide * (T / 2 + 0.02), head, 2.4).rotation.y = roomSide > 0 ? Math.PI : 0;

  const door = { x: d.x, z: d.z, u: 0, set: null };
  if (d.style === 'slide') {
    const off = -roomSide * (T / 2 + 0.06), half = (w - 0.24) / 2;
    const leaves = [-1, 1].map(s => {
      const leaf = group(s * half / 2 + s * 0.06, 0, off, frame);
      box(half, 2.3, 0.05, 0, 0, 1.15, 0, leaf, { material: glass, cast: false });
      for (const e of [-1, 1]) box(0.06, 2.3, 0.07, C.frame, e * half / 2, 1.15, 0, leaf, { cast: false });
      box(half, 0.08, 0.07, C.frame, 0, 2.27, 0, leaf, { cast: false });
      return { leaf, s, x: leaf.position.x };
    });
    door.set = u => leaves.forEach(l => { l.leaf.position.x = l.x + l.s * u * half * 0.95; });
  } else {
    const hinge = group(-w / 2 + 0.12, 0, 0, frame), lw = w - 0.26;
    const leafColor = d.style === 'glass' ? null : outer ? C.wood : 0xd9c3a5;
    if (leafColor === null) {
      box(lw, 2.3, 0.05, 0, lw / 2, 1.15, 0, hinge, { material: glass, cast: false });
      box(lw, 0.1, 0.07, C.frame, lw / 2, 2.25, 0, hinge, { cast: false });
    } else {
      box(lw, 2.3, 0.06, leafColor, lw / 2, 1.15, 0, hinge);
      box(lw * 0.6, 0.6, 0.07, 0xbfe3f2, lw / 2, 1.65, 0, hinge, { cast: false });
    }
    sph(0.05, 0xd4b062, lw - 0.12, 1.05, 0.06 * roomSide, hinge, { cast: false });
    door.set = u => { hinge.rotation.y = roomSide * 1.45 * u; };
  }
  office.doors.push(door);
}

// ---------- roof: flat, with skylights, units and the company sign ----------
const roof = office.roof = group(0, 0, 0, root);
box(maxX - minX + 1.2, 0.3, maxZ - minZ + 1.2, 0x8f97a3, CX, H + 0.15, CZ, roof);
for (const [x, z, w, d] of [[CX, minZ - 0.45, maxX - minX + 1.3, 0.3], [CX, maxZ + 0.45, maxX - minX + 1.3, 0.3], [minX - 0.45, CZ, 0.3, maxZ - minZ + 1.3], [maxX + 0.45, CZ, 0.3, maxZ - minZ + 1.3]]) {
  box(w, 0.6, d, C.trim, x, H + 0.6, z, roof);
}
for (const x of [-13, -6.5, 0, 6.5, 13]) box(3.2, 0.25, 2.2, 0xcfeaf5, x, H + 0.42, 1.2, roof, { glow: 0xfff0c8, cast: false });
for (const [x, z] of [[-14, -10], [-10, -10], [14, 13]]) { box(1.8, 0.9, 1.4, 0xc9ced6, x, H + 0.75, z, roof); cyl(0.45, 0.45, 0.06, 0x7a828e, x, H + 1.23, z, roof); }
for (let k = 0; k < 6; k++) { const panel = box(2.2, 0.06, 1.3, 0x2e4a7a, 4 + (k % 3) * 2.5, H + 0.62, -11 + Math.floor(k / 3) * 1.8, roof, { cast: false }); panel.rotation.x = -0.35; }
// entrance canopy
box(7, 0.18, 3.2, C.trim, 0, H - 0.05, maxZ + 1.6, roof);
for (const s of [-1, 1]) cyl(0.09, 0.09, H - 0.1, C.frame, s * 3.2, (H - 0.1) / 2, maxZ + 3, roof);
sign('🏢', 'Kantor Loker WFH', '#3f4a5a', '#ffffff', 0, H + 0.62, maxZ + 0.62, roof, 8);

// ---------- rooms ----------
const at = r => group((r.x0 + r.x1) / 2, 0, (r.z0 + r.z1) / 2, root);
const pendant = (x, z) => {
  const g = group(x, 0, z, upperRoot);
  cyl(0.015, 0.015, 0.6, 0x333333, 0, H - 0.3, 0, g, { cast: false });
  cyl(0.1, 0.38, 0.28, C.trim, 0, H - 0.72, 0, g, { cast: false });
  sph(0.13, 0xfff1c9, 0, H - 0.84, 0, g, { glow: 0xffd27a, cast: false });
  return g;
};
const ROOM_BUILD = { owner, meeting: rapat, toilet, focus: fokus, kantin, lobby: lobi, lounge: santai };
for (const [id, build] of Object.entries(ROOM_BUILD)) {
  const r = ROOMS[id], g = at(r);
  build(g, r);
  light(0, H - 0.6, 0, 0xffd9a0, 14, 12, g);
  pendant((r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2);
}

// ---------- division pods in the open-plan work room ----------
for (const pod of PODS) {
  const d = DIVS.find(x => x.id === pod.id);
  const g = group(pod.x, 0, pod.z, root);
  box(pod.width - 0.5, 0.02, 7.6, d.floor, 0, 0.045, 0.2, g, { cast: false });
  // a planter along the pod's front edge carries the division name
  box(3.6, 0.55, 0.45, 0xe9dccb, 0, 0.275, 3.95, g);
  box(3.5, 0.06, 0.38, 0x6f5a46, 0, 0.56, 3.95, g, { cast: false });
  for (let k = 0; k < 5; k++) sph(0.22, k % 2 ? 0x86c47c : 0x6fae6a, -1.4 + k * 0.7, 0.68, 3.95, g, { cast: false });
  solid(g, 0, 3.95, 3.6, 0.45);
  sign(d.icon, d.name.replace('Divisi ', ''), d.accent, '#ffffff', 0, 0.29, 4.19, g, 3.2);
  light(0, H - 0.6, 0, 0xffd9a0, 14, 12, g);
  for (const s of [-1, 1]) pendant(pod.x + s * pod.width / 4, pod.z);
  ({ cari, seleksi, tulis, lamar, pantau, freelance })[pod.id](g, d);
}
plant(-18.3, 7.3, root, 1.2); plant(18.3, 7.3, root, 1.2); plant(-18.3, -5.3, root, 1.1); plant(18.3, -5.3, root, 1.1);
for (const [x, z] of [[-18.3, 7.3], [18.3, 7.3], [-18.3, -5.3], [18.3, -5.3]]) solid(root, x, z, 0.8, 0.8);
// printer corner in the back corridor
box(1.1, 1, 0.7, 0xe7e9ee, -4.5, 0.5, -5.4, root); box(0.9, 0.1, 0.5, 0x3b3b48, -4.5, 1.05, -5.4, root, { cast: false });
solid(root, -4.5, -5.4, 1.1, 0.7);

// ---------- outside: walkways, planters, entrance sign ----------
path(0, maxZ + 6, 3.2, 12);
path(minX - 2.2, 0.6, 4.4, 2.6); path(maxX + 2.2, 0.6, 4.4, 2.6);
path(minX - 3.1, -8, 2.6, 19); path(maxX + 3.1, -8, 2.6, 19);
for (const s of [-1, 1]) {
  for (const x of [s * 5, s * 10, s * 15]) { box(2.6, 0.5, 0.8, 0xd9c7b0, x, 0.25, maxZ + 1.2); plant(x, maxZ + 1.2, scene, 0.8); solid(root, x, maxZ + 1.2, 2.6, 0.8); }
}
const totem = group(4.2, 0, maxZ + 8);
box(0.5, 2.2, 1.6, C.trim, 0, 1.1, 0, totem); sign('🏢', 'Loker WFH', '#3f4a5a', '#fff', 0.26, 1.6, 0, totem, 2.4).rotation.y = Math.PI / 2;
solid(root, 4.2, maxZ + 8, 0.5, 1.6);
