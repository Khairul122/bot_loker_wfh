// walking routes (A* over the whole island) and wall / furniture collision
import { V } from '../core/util.js';
import { createNavGrid, inRect } from '../domain/navgrid.js';

export { inOffice } from '../domain/office-plan.js';
export const inR = (x, z, r, m = 0.25) => inRect(x, z, r, m);

// [x0, x1, z0, z1] rects. Walls stop everyone; solids (desks, counters, beds…) are routed around
// and stop the owner's WASD walk, but people may still step onto a chair or sofa that sits in one.
export const WALLS = [];
export const SOLIDS = [];
let grid = null;
export function addWall(r) { WALLS.push(r); grid = null; }
export function addSolid(r) { SOLIDS.push(r); grid = null; }
const ISLAND = 46;
const nav = () => grid ||= createNavGrid({
  bounds: [-48, 48, -48, 48], walls: WALLS, solids: SOLIDS, open: (x, z) => x * x + z * z < ISLAND * ISLAND,
});

// Char path steps from `from` to `to`. `exact` walks the last bit onto the spot itself (a seat inside
// a sofa's rect); otherwise the walk ends on the nearest free floor. `prefer` (unit vector): the side
// of `to` to arrive from.
export function route(from, to, exact = false, prefer = null) {
  const pts = nav().findPath(from, to, { exact, prefer });
  if (!pts) return [{ p: V(to.x, to.z) }]; // boxed in: walk straight, collision still holds
  return pts.map(q => ({ p: V(q.x, q.z) }));
}
// the nearest spot a person can stand on, on the same side of any wall
export function snapFree(p) {
  const q = nav().nearestFree(p);
  return q ? V(q.x, q.z) : V(p.x, p.z);
}
export const isFree = p => nav().isFree(p);

// How deep (x, z) sits inside rect r grown by m; <= 0 is outside.
const depth = (r, x, z, m) => Math.min(x - r[0] + m, r[1] + m - x, z - r[2] + m, r[3] + m - z);
// A step may never enter a rect, nor go deeper into one it already overlaps (so nobody slides
// along inside a wall), but it may always back out of it.
function hits(rects, p, nx, nz, m) {
  for (const r of rects) {
    const d = depth(r, nx, nz, m);
    if (d > 0 && d >= depth(r, p.x, p.z, m)) return true;
  }
  return false;
}
export function blocked(p, nx, nz, { furniture = false } = {}) {
  if (nx * nx + nz * nz > 47 * 47) return true;
  return hits(WALLS, p, nx, nz, 0.25) || (furniture && hits(SOLIDS, p, nx, nz, 0.15));
}
