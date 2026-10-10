// walking routes (lift, around the tower) and wall collision
import { W, D, ELEV_X, DOOR_X, V, clamp } from '../core/util.js';

export const inTower = p => p.x > -W / 2 - 0.3 && p.x < W / 2 + 2.5 && p.z > -D / 2 - 0.4 && p.z < D / 2 + 0.4;
const FRONT_Z = D / 2 + 1.8;
function hitsTower(a, b) {
  for (let k = 1; k < 24; k++) {
    const u = k / 24, x = a.x + (b.x - a.x) * u, z = a.z + (b.z - a.z) * u;
    if (x > -W / 2 - 1 && x < W / 2 + 3 && z > -D / 2 - 1 && z < D / 2 + 1) return true;
  }
  return false;
}
function outdoorLeg(a, b) {
  // detour around the tower footprint when walking outside, only if the straight line would cross it
  const pts = [];
  if (!hitsTower(a, b)) return pts;
  const behind = p => p.z < -D / 2 - 0.4;
  const side = p => p.x < 0 ? -W / 2 - 2 : W / 2 + 3.6;
  if (behind(a) !== behind(b)) {
    const from = behind(a) ? a : b; const sx = side(from);
    const legs = [V(sx, from.z), V(sx, FRONT_Z)];
    if (!behind(a)) legs.reverse();
    pts.push(...legs);
  } else if (!behind(a) && Math.sign(a.x) !== Math.sign(b.x) && Math.min(a.z, b.z) < FRONT_Z && Math.abs(a.x) > W / 2 && Math.abs(b.x) > W / 2) {
    pts.push(V(side(a), FRONT_Z), V(side(b), FRONT_Z));
  }
  return pts;
}
export function route(fromLevel, from, toLevel, to) {
  const steps = []; const P = v => steps.push({ p: v });
  const fromIn = fromLevel > 0 || inTower(from), toIn = toLevel > 0 || inTower(to);
  if (fromLevel === 0 && !fromIn && (toIn || toLevel !== 0)) {
    outdoorLeg(from, V(from.x, FRONT_Z)).forEach(P);
    P(V(clamp(from.x, -W / 2 + 1, W / 2 - 1), FRONT_Z));
  }
  if (fromLevel !== toLevel) {
    P(V(DOOR_X, 0)); P(V(ELEV_X, 0)); steps.push({ ride: toLevel }); P(V(DOOR_X, 0));
  }
  if (toLevel === 0 && !toIn && (fromIn || fromLevel !== 0)) {
    P(V(clamp(to.x, -W / 2 + 1, W / 2 - 1), FRONT_Z));
    outdoorLeg(V(clamp(to.x, -W / 2 + 1, W / 2 - 1), FRONT_Z), to).forEach(P);
  } else if (fromLevel === 0 && toLevel === 0 && !fromIn && !toIn) {
    outdoorLeg(from, to).forEach(P);
  }
  P(to);
  return steps;
}

const WALLS = [
  [-W / 2 - 0.5, W / 2 + 0.5, -D / 2 - 0.5, -D / 2], [-W / 2 - 0.5, -W / 2, -D / 2 - 0.5, D / 2 + 0.5],
  [W / 2, W / 2 + 0.5, 2.6, 6.6], [W / 2, W / 2 + 0.5, -6.6, -2.6],
  [ELEV_X + 1.0, ELEV_X + 1.4, -1.4, 1.4], [W / 2 + 0.5, ELEV_X + 1.4, 1.2, 1.5], [W / 2 + 0.5, ELEV_X + 1.4, -1.5, -1.2],
];
// walls that exist on one level only (toilet room, houses): [x0, x1, z0, z1, level]
export const ROOM_WALLS = [];
export const inR = (x, z, r, m = 0.25) => x > r[0] - m && x < r[1] + m && z > r[2] - m && z < r[3] + m;
const inShaft = p => p.x > W / 2 - 0.2 && p.x < ELEV_X + 0.9 && Math.abs(p.z) < 1.1;
export const inLift = p => p.x > W / 2 + 0.7 && p.x < ELEV_X + 0.9 && Math.abs(p.z) < 1.1;
export function blocked(level, p, nx, nz) {
  if (level > 0) {
    const onFloor = nx > -W / 2 + 0.3 && nx < W / 2 + 0.3 && Math.abs(nz) < D / 2 - 0.3;
    if (!onFloor && !inShaft({ x: nx, z: nz })) return true;
  } else if (nx * nx + nz * nz > 47 * 47) return true;
  return WALLS.concat(ROOM_WALLS.filter(r => r[4] === level)).some(r => inR(nx, nz, r) && !inR(p.x, p.z, r));
}
