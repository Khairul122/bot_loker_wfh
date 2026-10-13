// shared building registries: desk seats, room spots, data-driven props, furniture footprints
import * as THREE from 'three';
import { addSolid, addWall } from '../world/navigation.js';
import { desk } from '../world/props.js';

export const deskSeats = {}; // division id -> [{x,z,ry}] in world space
export const roomSpots = []; // spots built together with their rooms, merged into `spots`
export const dyn = {}; // data-driven props, shown/hidden from the stats
// cut: meshes that shrink to waist height in the cutaway; upper: meshes hidden in it
export const cutaway = { cut: [], upper: [] };

const tmp = new THREE.Vector3();
const yawOf = o => { let r = 0; for (; o; o = o.parent) r += o.rotation.y; return r; };
export function toWorld(g, x, z) {
  g.updateWorldMatrix(true, false);
  tmp.set(x, 0, z).applyMatrix4(g.matrixWorld);
  return { x: tmp.x, z: tmp.z };
}
// a w × d piece of furniture centred at (x, z) in g, turned by ry: routes go around it
export function solid(g, x, z, w, d, ry = 0) {
  const c = toWorld(g, x, z), turned = Math.abs(Math.sin(yawOf(g) + ry)) > 0.5;
  const hw = (turned ? d : w) / 2, hd = (turned ? w : d) / 2;
  addSolid([c.x - hw, c.x + hw, c.z - hd, c.z + hd]);
}
// a wall given in g's local space (g must not be turned)
export function wall(g, x0, x1, z0, z1) {
  const a = toWorld(g, x0, z0), b = toWorld(g, x1, z1);
  addWall([Math.min(a.x, b.x), Math.max(a.x, b.x), Math.min(a.z, b.z), Math.max(a.z, b.z)]);
}
// a usable spot given in g's local space
export function spot(g, s) {
  const c = toWorld(g, s.x, s.z);
  const out = { level: 0, ...s, x: c.x, z: c.z, ry: (s.ry || 0) + yawOf(g) };
  roomSpots.push(out);
  return out;
}

// desks face the front so the camera sees faces; the seat sits behind the desk
export function seats(id, list, g, screen) {
  deskSeats[id] = list.map(([x, z]) => {
    desk(x, z, Math.PI, g, screen);
    solid(g, x, z, 1.8, 0.9);
    const c = toWorld(g, x, z - 0.75);
    return { x: c.x, z: c.z, ry: 0 };
  });
}
