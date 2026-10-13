// The single-storey office: footprint, rooms, doors and the wall lines between them.
// Pure data (no three.js) so tests can check that every room has a door and is reachable.
import { inRect } from './navgrid.js';
export const OFFICE = Object.freeze({ minX: -19, maxX: 19, minZ: -14, maxZ: 18, height: 3.2, wall: 0.3 });

const room = (id, name, icon, x0, x1, z0, z1, extra = {}) => Object.freeze({ id, name, icon, x0, x1, z0, z1, ...extra });
export const ROOMS = Object.freeze({
  owner: room('owner', 'Ruang Owner', '👑', -19, -7, -14, -6, { ownerOnly: true }),
  meeting: room('meeting', 'Ruang Rapat', '💬', -7, 5, -14, -6),
  toilet: room('toilet', 'Toilet', '🚻', 5, 10, -14, -6),
  focus: room('focus', 'Ruang Fokus', '📚', 10, 19, -14, -6),
  work: room('work', 'Ruang Kerja', '💼', -19, 19, -6, 8),
  kantin: room('kantin', 'Kantin', '🍜', -19, -6, 8, 18),
  lobby: room('lobby', 'Lobi', '🛎️', -6, 6, 8, 18),
  lounge: room('lounge', 'Ruang Santai', '🛋️', 6, 19, 8, 18),
});

// axis 'x': the door sits in a wall that runs along x (a wall at constant z); 'z' the other way.
// `to` lists the two spaces the door joins ('out' is the campus).
const door = (id, x, z, axis, width, to, style = 'swing') => Object.freeze({ id, x, z, axis, width, to, style });
export const DOORS = Object.freeze([
  door('main', 0, 18, 'x', 2.4, ['lobby', 'out'], 'slide'),
  door('west', -19, 0.6, 'z', 2, ['work', 'out']),
  door('east', 19, 0.6, 'z', 2, ['work', 'out']),
  door('lobby', 0, 8, 'x', 2.4, ['lobby', 'work'], 'slide'),
  door('kantin', -9, 8, 'x', 2, ['kantin', 'work']),
  door('lounge', 9, 8, 'x', 2, ['lounge', 'work']),
  door('owner', -11, -6, 'x', 2, ['owner', 'work']),
  door('meeting', 1.5, -6, 'x', 2, ['meeting', 'work'], 'glass'),
  door('toilet', 7.5, -6, 'x', 2, ['toilet', 'work']),
  door('focus', 14.5, -6, 'x', 2, ['focus', 'work']),
]);

// wall centre lines; exterior ones carry windows, `glass` ones are see-through partitions
const line = (x0, z0, x1, z1, kind) => Object.freeze({ x0, z0, x1, z1, kind });
const { minX, maxX, minZ, maxZ } = OFFICE;
export const WALL_LINES = Object.freeze([
  line(minX, minZ, maxX, minZ, 'exterior'),
  line(minX, maxZ, maxX, maxZ, 'facade'),
  line(minX, minZ, minX, maxZ, 'exterior'),
  line(maxX, minZ, maxX, maxZ, 'exterior'),
  line(minX, -6, -7, -6, 'interior'),
  line(-7, -6, 5, -6, 'glass'),
  line(5, -6, maxX, -6, 'interior'),
  line(-7, minZ, -7, -6, 'interior'),
  line(5, minZ, 5, -6, 'interior'),
  line(10, minZ, 10, -6, 'interior'),
  line(minX, 8, -6, 8, 'interior'),
  line(-6, 8, 6, 8, 'glass'),
  line(6, 8, maxX, 8, 'interior'),
  line(-6, 8, -6, maxZ, 'interior'),
  line(6, 8, 6, maxZ, 'interior'),
]);

// Division pods in the open-plan work room, left to right in company order.
export const PODS = Object.freeze([
  { id: 'cari', x: -15.2, width: 7.6 },
  { id: 'seleksi', x: -8.55, width: 5.7 },
  { id: 'tulis', x: -2.85, width: 5.7 },
  { id: 'lamar', x: 2.85, width: 5.7 },
  { id: 'pantau', x: 8.55, width: 5.7 },
  { id: 'freelance', x: 15.2, width: 7.6 },
].map(pod => Object.freeze({ ...pod, z: 0.7 })));
export const DESK_ROWS = Object.freeze({ back: -2.5, front: 2.5 }); // desk centres, relative to the pod centre

const onLine = (d, l) => d.axis === 'x'
  ? l.z0 === l.z1 && l.z0 === d.z && d.x - d.width / 2 >= Math.min(l.x0, l.x1) && d.x + d.width / 2 <= Math.max(l.x0, l.x1)
  : l.x0 === l.x1 && l.x0 === d.x && d.z - d.width / 2 >= Math.min(l.z0, l.z1) && d.z + d.width / 2 <= Math.max(l.z0, l.z1);

// Wall pieces as axis-aligned rects [x0, x1, z0, z1] with door gaps cut out, plus the gaps themselves.
export function wallPieces(lines = WALL_LINES, doors = DOORS, thickness = OFFICE.wall) {
  const half = thickness / 2;
  const pieces = [];
  for (const l of lines) {
    const alongX = l.z0 === l.z1;
    const a = Math.min(alongX ? l.x0 : l.z0, alongX ? l.x1 : l.z1) - (l.kind === 'interior' || l.kind === 'glass' ? 0 : half);
    const b = Math.max(alongX ? l.x0 : l.z0, alongX ? l.x1 : l.z1) + (l.kind === 'interior' || l.kind === 'glass' ? 0 : half);
    const gaps = doors.filter(d => onLine(d, l))
      .map(d => [(alongX ? d.x : d.z) - d.width / 2, (alongX ? d.x : d.z) + d.width / 2, d])
      .sort((p, q) => p[0] - q[0]);
    let from = a;
    const cut = (s, e, gapDoor) => {
      if (e - s < 0.01) return;
      const rect = alongX ? [s, e, l.z0 - half, l.z0 + half] : [l.x0 - half, l.x0 + half, s, e];
      pieces.push({ rect, kind: l.kind, alongX, door: gapDoor || null });
    };
    for (const [s, e, d] of gaps) { cut(from, s); cut(s, e, d); from = e; }
    cut(from, b);
  }
  return pieces;
}
export const wallRects = () => wallPieces().filter(p => !p.door).map(p => p.rect);

export const inOffice = p => inRect(p.x, p.z, [minX, maxX, minZ, maxZ], 0.2);
export const roomAt = p => Object.values(ROOMS).find(r => inRect(p.x, p.z, [r.x0, r.x1, r.z0, r.z1])) || null;

// Walls drop to waist height (and the roof lifts) whenever the owner looks into the office from above.
export const wallsCut = ({ fp, overview, inside }) => !fp && (overview || inside);
