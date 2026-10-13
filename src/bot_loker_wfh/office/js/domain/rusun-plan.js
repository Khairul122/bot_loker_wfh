// The rumah susun behind the office: Blok A (west) and Blok B (east), each a corridor with five units
// on either side, joined by a shared lobby that also holds the owner's unit and the laundry room.
// Pure data, like office-plan.js.
import { inRect } from './navgrid.js';
import { room, door, line } from './office-plan.js';

export const RUSUN = Object.freeze({ minX: -28.5, maxX: 28.5, minZ: -32.4, maxZ: -20, height: 3, wall: 0.3 });
const { minX, maxX, minZ, maxZ } = RUSUN;
export const UNIT = Object.freeze({ width: 4.5, depth: 5 });
const HALL = Object.freeze({ z0: -27.4, z1: -25 }); // the wing corridors
const LINK = 6; // the lobby spans x in [-LINK, LINK]
export const BLOCKS = Object.freeze([
  Object.freeze({ id: 'hallA', name: 'Blok A', x0: minX, x1: -LINK, color: 0xe7f1ec, accent: '#4f9a7d' }),
  Object.freeze({ id: 'hallB', name: 'Blok B', x0: LINK, x1: maxX, color: 0xf6e9dc, accent: '#c9774e' }),
]);

// Units in slot order: Blok A north 0-4, south 5-9, Blok B north 10-14, south 15-19, the owner's 20.
// `side` is where its corridor door is: +1 toward +z, -1 toward -z. doorX sits 1.1 m off centre.
export const UNITS = Object.freeze([
  ...BLOCKS.flatMap(b => [-1, 1].flatMap(side => Array.from({ length: 5 }, (_, k) => {
    const x0 = b.x0 + k * UNIT.width, z0 = side < 0 ? HALL.z1 : minZ;
    return { block: b.id, x0, x1: x0 + UNIT.width, z0, z1: z0 + UNIT.depth, side: side < 0 ? -1 : 1 };
  }))),
  { block: 'lobby', x0: -LINK, x1: -1.5, z0: minZ, z1: HALL.z0, side: 1 },
].map((u, slot) => {
  const cx = (u.x0 + u.x1) / 2;
  return Object.freeze({ ...u, slot, id: `u${slot}`, cx, cz: (u.z0 + u.z1) / 2, doorX: cx + 1.1 * u.side, doorZ: u.side > 0 ? u.z1 : u.z0 });
}));
export const OWNER_SLOT = 20;

export const ROOMS = Object.freeze({
  lobby: room('lobby', 'Lobi Rusun', '🏢', -LINK, LINK, HALL.z0, maxZ, { hall: true }),
  laundry: room('laundry', 'Ruang Cuci', '🧺', -1.5, LINK, minZ, HALL.z0),
  ...Object.fromEntries(BLOCKS.map(b => [b.id, room(b.id, b.name, '🏘️', b.x0, b.x1, HALL.z0, HALL.z1, { hall: true })])),
  ...Object.fromEntries(UNITS.map(u => [u.id, room(u.id, `Unit ${u.slot + 1}`, '🏠', u.x0, u.x1, u.z0, u.z1, { unit: u })])),
});

const hallOf = u => u.block === 'lobby' ? 'lobby' : u.block;
export const DOORS = Object.freeze([
  door('rusun-main', 0, maxZ, 'x', 2.4, ['lobby', 'out'], 'slide'),
  door('rusun-west', minX, (HALL.z0 + HALL.z1) / 2, 'z', 1.6, ['hallA', 'out']),
  door('rusun-east', maxX, (HALL.z0 + HALL.z1) / 2, 'z', 1.6, ['hallB', 'out']),
  door('link-a', -LINK, (HALL.z0 + HALL.z1) / 2, 'z', 1.6, ['hallA', 'lobby'], 'glass'),
  door('link-b', LINK, (HALL.z0 + HALL.z1) / 2, 'z', 1.6, ['hallB', 'lobby'], 'glass'),
  door('laundry', 3.5, HALL.z0, 'x', 1.6, ['laundry', 'lobby']),
  ...UNITS.map(u => door(`unit-${u.slot}`, u.doorX, u.doorZ, 'x', 1.6, [u.id, hallOf(u)])),
]);

const dividers = BLOCKS.flatMap(b => [1, 2, 3, 4].map(k => b.x0 + k * UNIT.width))
  .flatMap(x => [line(x, HALL.z1, x, maxZ, 'interior'), line(x, minZ, x, HALL.z0, 'interior')]);
export const WALL_LINES = Object.freeze([
  line(minX, minZ, maxX, minZ, 'plain'),
  line(minX, maxZ, -LINK, maxZ, 'plain', BLOCKS[0].color),
  line(-LINK, maxZ, LINK, maxZ, 'facade'),
  line(LINK, maxZ, maxX, maxZ, 'plain', BLOCKS[1].color),
  line(minX, minZ, minX, maxZ, 'plain', BLOCKS[0].color),
  line(maxX, minZ, maxX, maxZ, 'plain', BLOCKS[1].color),
  line(minX, HALL.z1, -LINK, HALL.z1, 'interior'),
  line(LINK, HALL.z1, maxX, HALL.z1, 'interior'),
  line(minX, HALL.z0, maxX, HALL.z0, 'interior'),
  ...[-LINK, LINK].flatMap(x => [line(x, HALL.z1, x, maxZ, 'interior'), line(x, HALL.z0, x, HALL.z1, 'glass'), line(x, minZ, x, HALL.z0, 'interior')]),
  line(-1.5, minZ, -1.5, HALL.z0, 'interior'),
  ...dividers,
]);

export const inRusun = p => inRect(p.x, p.z, [minX, maxX, minZ, maxZ], 0.2);
