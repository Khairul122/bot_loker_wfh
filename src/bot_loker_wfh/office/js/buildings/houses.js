// ---------- rumah susun: Blok A and Blok B joined by a shared lobby; one furnished unit per person ----------
// `houses` keeps one entry per unit (bed, TV, fridge spots, window light) for the AI and the owner.
import * as THREE from 'three';
import { scene, light } from '../core/engine.js';
import { gradient, box, cyl, sph, group, sign, tag, walkables } from '../core/factory.js';
import { RUSUN, UNITS, ROOMS, DOORS, WALL_LINES, BLOCKS, OWNER_SLOT, inRusun } from '../domain/rusun-plan.js';
import { lamp, rug, path, plant, sofa } from '../world/props.js';
import { inR } from '../world/navigation.js';
import { spots } from '../world/spots.js';
import { staff } from '../characters/team.js';
import { me, myLook } from '../characters/player.js';
import { solid, toWorld } from './registry.js';
import { buildShell, glass } from './shell.js';

const { minX, maxX, minZ, maxZ, height: H, wall: T } = RUSUN;
const CX = (minX + maxX) / 2, CZ = (minZ + maxZ) / 2;
export const houses = [];
export const rusun = { cut: [], upper: [], doors: [], roof: null, cutScale: 0.35, inside: inRusun };
const root = group(0, 0, 0, scene);
const upper = group(0, 0, 0, root); rusun.upper.push(upper);
const addSpot = s => { const out = { level: 0, by: null, id: spots.length, ...s }; spots.push(out); return out; };
const spotAt = (g, s) => { const c = toWorld(g, s.x, s.z); return addSpot({ ...s, x: c.x, z: c.z, ry: (s.ry || 0) + g.rotation.y }); };

// ---------- floor, walls, doors ----------
const slab = box(maxX - minX + 0.6, 0.4, maxZ - minZ + 0.6, 0xd6cfc6, CX, -0.18, CZ, root);
walkables.push({ mesh: slab, level: 0 });
const people = [...staff.map(c => ({ who: c, name: c.name, color: c.look.shirt })), { who: me, name: myLook.name, color: parseInt(myLook.shirt.slice(1), 16) || 0xffb26b }];
const roomsNamed = { ...ROOMS };
UNITS.forEach(u => { const p = people[u.slot]; roomsNamed[u.id] = { ...ROOMS[u.id], name: p.name, icon: u.slot === OWNER_SLOT ? '👑' : '🏠' }; });
buildShell({ root, upper, cut: rusun.cut, doors: rusun.doors }, { lines: WALL_LINES, doors: DOORS, rooms: roomsNamed, height: H, thickness: T });
const floorOf = r => box(r.x1 - r.x0 - T, 0.02, r.z1 - r.z0 - T, r.color, (r.x0 + r.x1) / 2, 0.03, (r.z0 + r.z1) / 2, root, { cast: false });
floorOf({ ...ROOMS.lobby, color: 0xf3ede4 }); floorOf({ ...ROOMS.laundry, color: 0xe3f1f4 });
for (const b of BLOCKS) {
  floorOf({ ...ROOMS[b.id], color: 0xdcd6cc });
  const c = (b.x0 + b.x1) / 2;
  light(c, H - 0.6, -26.2, 0xffd9a0, 12, 12);
  for (const x of [c - 6, c, c + 6]) sph(0.14, 0xfff1c9, x, H - 0.15, -26.2, upper, { glow: 0xffd27a, cast: false });
}

// ---------- one unit: bed, sofa + TV, fridge, lamp and a window that lights up while someone is home ----------
// built in the unit's own frame: local +z faces its corridor door
function buildUnit(u, { who, name, color }) {
  const g = group(u.cx, 0, u.cz, root, u.side > 0 ? 0 : Math.PI);
  const block = BLOCKS.find(b => b.id === u.block);
  const h = { name, who, x: u.cx, z: u.cz, front: u.doorZ, doorX: u.doorX, box: [u.x0, u.x1, u.z0, u.z1], unit: u };
  tag(box(4.2, 0.02, 4.7, block ? block.color : 0xf2e6d6, 0, 0.03, 0, g, { cast: false }), { kind: 'house', house: h });
  rug(0.4, 0.4, 1, 0xf6c89f, g);
  h.win = new THREE.MeshToonMaterial({ color: 0xbfe3f2, gradientMap: gradient, emissive: new THREE.Color(0xffc56b), emissiveIntensity: 0 });
  const winG = group(0, 0, 0, g); rusun.upper.push(winG); // hidden with the walls in the cutaway
  box(1.6, 1.1, T + 0.08, 0, 0.3, 1.7, -2.5, winG, { material: h.win, cast: false });
  const bed = group(-1.4, 0, -1.3, g);
  box(1.3, 0.35, 2.1, 0x9a6b4a, 0, 0.18, 0, bed); box(1.2, 0.25, 2, 0xffffff, 0, 0.47, 0, bed);
  box(0.8, 0.14, 0.4, 0xfff6e0, 0, 0.66, -0.75, bed); box(1.22, 0.08, 1.2, color, 0, 0.63, 0.35, bed);
  solid(g, -1.4, -1.3, 1.3, 2.1);
  const tvG = group(1.2, 0, -2.1, g);
  box(1.2, 0.5, 0.4, 0x8a6b55, 0, 0.25, 0, tvG); box(1.4, 0.8, 0.08, 0x2b2b35, 0, 1.1, 0, tvG);
  h.tvMat = new THREE.MeshBasicMaterial({ color: 0x15151c });
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(1.26, 0.68), h.tvMat); screen.position.set(0, 1.1, 0.05); tvG.add(screen);
  solid(g, 1.2, -2.1, 1.2, 0.4);
  const sofaG = group(1.2, 0, 0.2, g);
  box(1.5, 0.4, 0.7, block ? 0x7aa6d8 : 0x7a5a8a, 0, 0.3, 0, sofaG); box(1.5, 0.6, 0.2, block ? 0x7aa6d8 : 0x7a5a8a, 0, 0.7, 0.3, sofaG);
  const fridge = group(-1.75, 0, 1.95, g);
  box(0.7, 1.7, 0.6, 0xf4f7fa, 0, 0.85, 0, fridge); box(0.04, 0.5, 0.05, 0x9aa3ad, 0.36, 1.1, -0.2, fridge);
  solid(g, -1.75, 1.95, 0.7, 0.6);
  const lampG = group(0.2, 0, -2.05, g); cyl(0.04, 0.05, 1.5, 0x5a4a42, 0, 0.75, 0, lampG); sph(0.2, 0, 0, 1.6, 0, lampG, { material: h.win });
  h.bed = spotAt(g, { kind: 'kasur', x: -1.4, z: -0.3, ry: 0, pose: 'lie', emo: '😴', energy: 14, house: h });
  h.tv = spotAt(g, { kind: 'tv', x: 1.2, z: 0.15, ry: Math.PI, pose: 'sit', emo: '📺', joy: 4, energy: 3, house: h });
  h.fridge = spotAt(g, { kind: 'kulkas', x: -1, z: 1.95, ry: -Math.PI / 2, pose: 'stand', emo: '🥤', energy: 8, house: h });
  tag(bed, { kind: 'spot', kindName: 'kasur', house: h }); tag(sofaG, { kind: 'spot', kindName: 'tv', house: h }); tag(tvG, { kind: 'spot', kindName: 'tv', house: h });
  tag(fridge, { kind: 'spot', kindName: 'kulkas', house: h });
  houses.push(h);
  return h;
}
for (const u of UNITS) { const p = people[u.slot]; p.who.home = buildUnit(u, p); }

// ---------- shared lobby: resident board, mailboxes, vending machine, waiting sofa ----------
const lobby = group(0, 0, -23.7, root);
rug(0, 0.3, 2, 0xf6c89f, lobby);
const vend = group(-4.5, 0, 3.15, lobby);
box(1, 1.9, 0.7, 0xd8643a, 0, 0.95, 0, vend); box(0.7, 1, 0.04, 0xcfeaf5, -0.08, 1.2, -0.37, vend, { glow: 0xdff4ff, cast: false });
tag(vend, { kind: 'spot', kindName: 'minum' }); solid(lobby, -4.5, 3.15, 1, 0.7);
spotAt(lobby, { kind: 'minum', x: -4.5, z: 2.3, ry: 0, pose: 'stand', emo: '🥤', energy: 6 });
// one mailbox per unit; its flag is up while the resident is home
const mail = group(-5.6, 0, 0.3, lobby);
box(0.45, 1.5, 2.5, 0x8a6b55, 0, 0.75, 0, mail); solid(lobby, -5.6, 0.3, 0.45, 2.5);
UNITS.forEach((u, k) => {
  const y = 0.35 + Math.floor(k / 7) * 0.42, z = -1.05 + (k % 7) * 0.35;
  box(0.04, 0.34, 0.3, 0xe9dccb, 0.24, y, z, mail, { cast: false });
  houses[k].flag = box(0.03, 0.1, 0.05, 0xef6a5a, 0.27, y + 0.12, z + 0.1, mail, { cast: false });
});
// resident board: who is home, asleep or at the office, redrawn by systems/life.js
const board = { canvas: document.createElement('canvas'), tex: null };
board.canvas.width = 1024; board.canvas.height = 600;
board.tex = new THREE.CanvasTexture(board.canvas); board.tex.colorSpace = THREE.SRGBColorSpace;
const bg = group(-2.6, 0, -0.9, lobby);
for (const s of [-1, 1]) box(0.08, 2.2, 0.08, 0x3f4a5a, s * 1.3, 1.1, 0, bg);
box(2.6, 1.6, 0.08, 0x3f4a5a, 0, 1.45, 0, bg);
const boardMesh = new THREE.Mesh(new THREE.PlaneGeometry(2.45, 1.44), new THREE.MeshBasicMaterial({ map: board.tex }));
boardMesh.position.set(0, 1.45, 0.05); bg.add(boardMesh);
solid(lobby, -2.6, -0.9, 2.7, 0.3);
export function drawResidents(statusOf) {
  const g = board.canvas.getContext('2d');
  g.fillStyle = '#fffaf2'; g.fillRect(0, 0, 1024, 600);
  g.fillStyle = '#3f4a5a'; g.font = '900 40px Nunito, sans-serif'; g.textBaseline = 'middle';
  g.fillText('🏢 Papan Penghuni', 28, 40);
  houses.forEach((h, i) => {
    const col = Math.floor(i / 11), row = i % 11, x = 28 + col * 500, y = 100 + row * 45;
    const st = statusOf(h);
    g.fillStyle = st.color; g.beginPath(); g.arc(x + 12, y, 10, 0, 7); g.fill();
    g.fillStyle = '#3f4a5a'; g.font = '800 28px Nunito, sans-serif'; g.fillText(h.name, x + 34, y);
    g.fillStyle = '#7a8a84'; g.font = '700 24px Nunito, sans-serif'; g.fillText(st.label, x + 210, y);
  });
  board.tex.needsUpdate = true;
}
tag(sofa(5.3, 1.1, -Math.PI / 2, lobby, 0x7aa6d8), { kind: 'spot', kindName: 'sofa' }); solid(lobby, 5.3, 1.1, 2.4, 0.9, -Math.PI / 2);
for (const z of [0.5, 1.7]) spotAt(lobby, { kind: 'sofa', x: 5.2, z, ry: -Math.PI / 2, pose: 'sit', emo: '🛋️', energy: 6 });
box(0.6, 0.4, 1.1, 0xc89a6c, 4, 0.2, 1.1, lobby); solid(lobby, 4, 1.1, 0.6, 1.1);
plant(5.4, 3.1, lobby, 1.2); solid(lobby, 5.4, 3.1, 0.8, 0.8);
plant(0.9, -3.2, lobby); solid(lobby, 0.9, -3.2, 0.6, 0.6);
light(0, H - 0.6, 0, 0xffd9a0, 14, 12, lobby);

// ---------- laundry: washing machines whose drums turn while someone does the washing ----------
const laundry = group(2.25, 0, -29.9, root);
const washers = [-2.25, -1.05, 0.15].map(x => {
  const m = group(x, 0, -1.85, laundry);
  box(0.9, 0.9, 0.8, 0xf4f7fa, 0, 0.45, 0, m);
  const drum = group(0, 0.48, 0.41, m);
  cyl(0.3, 0.3, 0.03, 0, 0, 0, 0, drum, { material: glass, cast: false }).rotation.x = Math.PI / 2;
  box(0.5, 0.05, 0.02, 0x9aa3ad, 0, 0, 0.02, drum, { cast: false });
  tag(m, { kind: 'spot', kindName: 'cuci' });
  const s = spotAt(laundry, { kind: 'cuci', x, z: -0.95, ry: Math.PI, pose: 'stand', emo: '🧺', joy: 1 });
  return { drum, s };
});
solid(laundry, -1.05, -1.85, 3.3, 0.8);
box(1.4, 0.08, 0.8, 0xc89a6c, 2.3, 0.8, -0.7, laundry); for (const [a, b] of [[-0.6, -0.3], [0.6, -0.3], [-0.6, 0.3], [0.6, 0.3]]) box(0.06, 0.8, 0.06, 0x8a6b55, 2.3 + a, 0.4, -0.7 + b, laundry);
solid(laundry, 2.3, -0.7, 1.4, 0.8);
box(0.6, 0.35, 0.45, 0xd9b48a, 2.3, 1.02, -0.7, laundry, { cast: false });
light(0, H - 0.6, 0, 0xffd9a0, 10, 10, laundry);
export function updateLaundry(t) {
  for (const w of washers) if (w.s.by && w.s.by.spot === w.s) w.drum.rotation.z = t * 6;
}

// ---------- roof: one roof per block in its own colour, a lower glass roof over the lobby ----------
const roof = rusun.roof = group(0, 0, 0, root);
for (const b of BLOCKS) {
  const w = b.x1 - b.x0 + 0.6, c = (b.x0 + b.x1) / 2;
  box(w, 0.3, maxZ - minZ + 0.8, 0x9aa1ab, c, H + 0.15, CZ, roof);
  for (const z of [minZ - 0.3, maxZ + 0.3]) box(w, 0.6, 0.25, parseInt(b.accent.slice(1), 16), c, H + 0.55, z, roof);
  for (const x of [b.x0 - 0.2, b.x1 + 0.2]) box(0.25, 0.6, maxZ - minZ + 0.8, parseInt(b.accent.slice(1), 16), x, H + 0.55, CZ, roof);
  cyl(0.7, 0.7, 1.3, 0xc9ced6, c - 5, H + 0.95, CZ - 2, roof); cyl(0.7, 0.7, 1.3, 0xc9ced6, c + 5, H + 0.95, CZ - 2, roof);
  sign('🏘️', b.name, b.accent, '#fff', c, H + 0.6, maxZ + 0.45, roof, 4);
}
box(12.4, 0.2, maxZ - minZ + 0.6, 0, 0, H - 0.1, CZ, roof, { material: glass, cast: false });
for (const x of [-5.8, 5.8]) box(0.2, 0.3, maxZ - minZ + 0.6, 0x55606e, x, H, CZ, roof, { cast: false });
box(5, 0.16, 2.6, 0x3f4a5a, 0, H - 0.05, maxZ + 1.4, roof);
for (const s of [-1, 1]) cyl(0.08, 0.08, H - 0.1, 0x55606e, s * 2.3, (H - 0.1) / 2, maxZ + 2.5, roof);
sign('🏢', 'Rusun Loker WFH', '#3f4a5a', '#fff', 0, H + 0.35, maxZ + 2.72, roof, 4.6);

// ---------- outside ----------
path(0, -17, 64, 2.6); path(minX - 2.5, -25.5, 2.6, 18); path(maxX + 2.5, -25.5, 2.6, 18);
for (const [x, z] of [[-15.5, -15.4], [15.5, -15.4], [minX - 3, -30], [maxX + 3, -30], [-8, -18.6], [8, -18.6]]) lamp(x, z, scene, 2.8);
for (const x of [-20, -13, 13, 20]) { box(2.4, 0.45, 0.7, 0xd9c7b0, x, 0.22, maxZ + 0.9); plant(x, maxZ + 0.9, scene, 0.7); solid(root, x, maxZ + 0.9, 2.4, 0.7); }

// which unit the owner is standing in, if any
export const unitAt = p => houses.find(h => inR(p.x, p.z, h.box, 0)) || null;
