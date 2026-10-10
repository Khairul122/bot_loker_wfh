// one office floor shell (slab, walls, windows, lift door, sign, lights) + shared building registries
import { light } from '../core/engine.js';
import { box, group, sign, walkables } from '../core/factory.js';
import { FH, W, D, V } from '../core/util.js';
import { desk } from '../world/props.js';

export const floors = [];
export const deskSeats = {}; // division id -> [{x,z,ry}]
export const roomSpots = []; // spots built together with their rooms, merged into `spots`
export const dyn = {}; // data-driven props, shown/hidden from the stats

export function buildFloor(i, d) {
  const g = group(0, i * FH, 0);
  // ground floor sits 2cm above the grass so the two planes never z-fight
  const slab = box(W + 0.8, 0.4, D + 0.8, d.floor, 0, i ? -0.2 : -0.18, 0, g);
  walkables.push({ mesh: slab, level: i });
  // back wall with windows
  box(W + 0.8, FH - 0.4, 0.3, d.wall, 0, (FH - 0.4) / 2, -D / 2 - 0.25, g);
  for (let k = -3; k <= 3; k++) {
    box(1.8, 1.5, 0.06, 0xbfe3f2, k * 2.4, 2.1, -D / 2 - 0.08, g, { glow: 0xffd89a, cast: false });
  }
  box(0.3, FH - 0.4, D + 0.8, d.wall, -W / 2 - 0.25, (FH - 0.4) / 2, 0, g); // left wall
  box(0.3, FH - 0.4, 4, d.wall, W / 2 + 0.25, (FH - 0.4) / 2, -4.6, g); // right stub
  box(0.3, FH - 0.4, 4, d.wall, W / 2 + 0.25, (FH - 0.4) / 2, 4.6, g);
  // the strips beside and above the lift door, the threshold and the cheeks up to the glass:
  // without them the floor shows holes around the lift
  for (const s of [-1, 1]) box(0.3, FH - 0.4, 1.4, d.wall, W / 2 + 0.25, (FH - 0.4) / 2, s * 1.9, g);
  box(0.3, FH - 3, 2.4, d.wall, W / 2 + 0.25, 2.6 + (FH - 3) / 2, 0, g);
  box(0.6, 0.4, 2.6, d.floor, W / 2 + 0.6, i ? -0.2 : -0.18, 0, g, { cast: false });
  for (const s of [-1, 1]) box(0.45, FH - 0.4, 0.12, 0xe4eef3, W / 2 + 0.62, (FH - 0.4) / 2, s * 1.26, g);
  box(0.45, 0.12, 2.6, 0xe4eef3, W / 2 + 0.62, FH - 0.46, 0, g, { cast: false });
  light(0, i * FH + FH - 0.9, 0.5, 0xffd9a0, 22, 15); // in the scene, not the floor group: the cutaway must not change the light count
  box(W + 0.8, 0.14, 0.14, 0xffffff, 0, FH - 0.5, D / 2 + 0.3, g, { cast: false }); // front beam
  // in front of the window glass (front face at -D/2 - 0.05), otherwise the two z-fight
  sign(d.icon, d.name, d.accent, '#ffffff', -3.5, FH - 1.05, -D / 2 + 0.03, g, 7.5);
  // ceiling lights
  for (let k = -1; k <= 1; k++) box(2.5, 0.08, 0.5, 0xffffff, k * 5, FH - 0.45, 0, g, { glow: 0xfff0c8, cast: false });
  floors.push(g);
  return g;
}

// desks are turned toward the front so the camera sees faces; the seat sits behind the desk
export function seats(id, list, g, screen) {
  deskSeats[id] = list.map(([x, z]) => { desk(x, z, Math.PI, g, screen); return { x, z: z - 0.75, ry: 0, side: 1.4 }; });
}
// the way out from behind a desk, walked in reverse on the way in
export const seatVia = s => [V(s.x + s.side, s.z + 2.4), V(s.x + s.side, s.z)];
