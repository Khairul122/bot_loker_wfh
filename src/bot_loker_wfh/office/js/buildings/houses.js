// ---------- housing estate: one house per character, behind the office ----------
import * as THREE from 'three';
import { scene } from '../core/engine.js';
import { gradient, add, box, cyl, sph, group, sign, tag } from '../core/factory.js';
import { V } from '../core/util.js';
import { lamp, rug, path } from '../world/props.js';
import { ROOM_WALLS } from '../world/navigation.js';
import { spots } from '../world/spots.js';
import { staff } from '../characters/team.js';
import { me, myLook } from '../characters/player.js';

export const houses = [];
const HOUSE_ROWS = [{ z: -21, street: -16.5 }, { z: -31, street: -26 }];
const EDGE_X = 29.5;
function buildHouse(slot, name, color) {
  const row = slot < 9 ? 0 : 1, hx = -24.8 + (slot % 9) * 6.2, hz = HOUSE_ROWS[row].z, front = hz + 2.5;
  const g = group(hx, 0, hz), wall = 0xfdf3e4;
  box(5, 0.1, 5, 0xd9b48a, 0, 0.05, 0, g, { cast: false });
  box(5.2, 2.6, 0.2, wall, 0, 1.3, -2.5, g);
  for (const s of [-1, 1]) box(0.2, 2.6, 5.2, wall, s * 2.5, 1.3, 0, g);
  for (const s of [-1, 1]) box(1.9, 2.6, 0.2, wall, s * 1.6, 1.3, 2.5, g);
  box(1.2, 0.6, 0.2, wall, 0, 2.3, 2.5, g);
  // windows + lamp share one material: lit at night while the occupant is home and awake
  const win = new THREE.MeshToonMaterial({ color: 0xbfe3f2, gradientMap: gradient, emissive: new THREE.Color(0xffc56b), emissiveIntensity: 0 });
  for (const s of [-1, 1]) box(0.9, 0.8, 0.05, 0, s * 1.6, 1.5, 2.62, g, { material: win, cast: false });
  box(0.05, 0.8, 1.2, 0, 2.62, 1.5, -0.6, g, { material: win, cast: false });
  const roof = add(new THREE.ConeGeometry(3.9, 1.7, 4), color, 0, 3.45, 0, g); roof.rotation.y = Math.PI / 4;
  const chimney = box(0.4, 0.9, 0.4, 0xb98d63, 1.2, 3.8, -1, g);
  const door = group(-0.6, 0, 2.5, g); box(1.2, 2, 0.08, 0x9a6b4a, 0.6, 1, 0, door);
  sign('🏠', name, '#' + color.toString(16).padStart(6, '0'), '#fff', 0, 2.3, 2.64, g, 2.2);
  const bed = group(-1.35, 0, -1.25, g);
  box(1.3, 0.35, 2.1, 0x9a6b4a, 0, 0.18, 0, bed); box(1.2, 0.25, 2, 0xffffff, 0, 0.47, 0, bed);
  box(0.8, 0.14, 0.4, 0xfff6e0, 0, 0.66, -0.75, bed); box(1.22, 0.08, 1.2, color, 0, 0.63, 0.35, bed);
  const sofaG = group(1.3, 0, 0.9, g);
  box(1.6, 0.4, 0.7, 0x7aa6d8, 0, 0.3, 0, sofaG); box(1.6, 0.6, 0.2, 0x7aa6d8, 0, 0.7, 0.3, sofaG);
  const tvG = group(1.3, 0, -2.2, g);
  box(1.2, 0.5, 0.4, 0x8a6b55, 0, 0.25, 0, tvG); box(1.5, 0.85, 0.08, 0x2b2b35, 0, 1.15, 0, tvG);
  const tvMat = new THREE.MeshBasicMaterial({ color: 0x15151c });
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(1.36, 0.72), tvMat); screen.position.set(0, 1.15, 0.05); tvG.add(screen);
  const fridge = group(-1.95, 0, 1.6, g);
  box(0.7, 1.7, 0.65, 0xf4f7fa, 0, 0.85, 0, fridge); box(0.04, 0.5, 0.05, 0x9aa3ad, 0.36, 1.1, 0.2, fridge);
  const lampG = group(0.2, 0, -2.0, g); cyl(0.04, 0.05, 1.5, 0x5a4a42, 0, 0.75, 0, lampG); sph(0.2, 0, 0, 1.6, 0, lampG, { material: win });
  rug(0.4, 0.4, 1.1, 0xf6c89f, g);
  const sx = hx <= 0 ? -EDGE_X : EDGE_X;
  const via = row === 0 ? [V(hx, HOUSE_ROWS[0].street), V(hx, front + 0.9), V(hx, front - 0.7)]
    : [V(sx, HOUSE_ROWS[0].street), V(sx, HOUSE_ROWS[1].street), V(hx, HOUSE_ROWS[1].street), V(hx, front + 0.9), V(hx, front - 0.7)];
  const hb = [hx - 2.5, hx + 2.5, hz - 2.5, hz + 2.5];
  ROOM_WALLS.push([hx - 2.6, hx + 2.6, hz - 2.6, hz - 2.4, 0], [hx - 2.6, hx - 2.4, hz - 2.6, hz + 2.6, 0], [hx + 2.4, hx + 2.6, hz - 2.6, hz + 2.6, 0],
    [hx - 2.6, hx - 0.6, front - 0.1, front + 0.1, 0], [hx + 0.6, hx + 2.6, front - 0.1, front + 0.1, 0]);
  const h = { name, x: hx, z: hz, front, roof, chimney, door, win, tvMat, via, box: hb, who: null };
  const sp = (kind, x, z, ry, pose, emo, extra) => { const s = { kind, level: 0, x: hx + x, z: hz + z, ry, pose, emo, house: h, via, box: hb, by: null, id: spots.length, ...extra }; spots.push(s); return s; };
  h.bed = sp('kasur', -1.35, -0.25, 0, 'lie', '😴', { energy: 14 });
  h.tv = sp('tv', 1.3, 0.85, Math.PI, 'sit', '📺', { joy: 4, energy: 3 });
  h.fridge = sp('kulkas', -1.15, 1.6, -Math.PI / 2, 'stand', '🥤', { energy: 8 });
  tag(bed, { kind: 'spot', kindName: 'kasur', house: h }); tag(sofaG, { kind: 'spot', kindName: 'tv', house: h }); tag(tvG, { kind: 'spot', kindName: 'tv', house: h });
  tag(fridge, { kind: 'spot', kindName: 'kulkas', house: h }); tag(roof, { kind: 'house', house: h }); tag(door, { kind: 'house', house: h });
  houses.push(h);
  return h;
}
// the owner lives in the middle of the first row, right behind the office
staff.forEach((c, i) => { c.home = buildHouse(i < 4 ? i : i + 1, c.name, c.look.shirt); c.home.who = c; });
me.home = buildHouse(4, myLook.name, parseInt(myLook.shirt.slice(1), 16) || 0xffb26b); me.home.who = me;
for (const [x, z] of [[-15.5, -15.4], [15.5, -15.4], [-EDGE_X - 1.3, -21], [EDGE_X + 1.3, -21]]) lamp(x, z, scene, 2.8);
path(0, -16.5, 2 * EDGE_X + 2, 2.6); path(0, -26, 2 * EDGE_X + 2, 2.6); path(-EDGE_X, -21.2, 2.6, 12); path(EDGE_X, -21.2, 2.6, 12);
sign('🏘️', 'Komplek Rumah', '#d98b5f', '#fff', 0, 3.2, -14.9, scene, 4.4);
