import test from 'node:test';
import assert from 'node:assert/strict';
import { RUSUN, UNITS, ROOMS, DOORS, WALL_LINES, BLOCKS, OWNER_SLOT } from '../../src/bot_loker_wfh/office/js/domain/rusun-plan.js';
import { OFFICE, wallPieces, wallRects as officeWalls } from '../../src/bot_loker_wfh/office/js/domain/office-plan.js';
import { createNavGrid, segmentHitsRect } from '../../src/bot_loker_wfh/office/js/domain/navgrid.js';

const walls = [...wallPieces(WALL_LINES, DOORS).filter(p => !p.door).map(p => p.rect), ...officeWalls()];
const grid = createNavGrid({ bounds: [-48, 48, -48, 48], walls, open: (x, z) => Math.hypot(x, z) < 46 });

test('one unit for each of the 20 employees plus the owner, in two blocks joined by a lobby', () => {
  assert.equal(UNITS.length, 21);
  assert.equal(OWNER_SLOT, UNITS.length - 1);
  assert.deepEqual(BLOCKS.map(b => UNITS.filter(u => u.block === b.id).length), [10, 10]);
  assert.ok(DOORS.some(d => d.to.includes('hallA') && d.to.includes('lobby')));
  assert.ok(DOORS.some(d => d.to.includes('hallB') && d.to.includes('lobby')));
});

test('the building stays on the island, behind the office, with a street between them', () => {
  for (const x of [RUSUN.minX, RUSUN.maxX]) for (const z of [RUSUN.minZ, RUSUN.maxZ]) assert.ok(Math.hypot(x, z) < 44);
  assert.ok(OFFICE.minZ - RUSUN.maxZ >= 5);
});

test('every unit and room has a door cut into a wall', () => {
  for (const id of Object.keys(ROOMS)) assert.ok(DOORS.some(d => d.to.includes(id)), `${id} has a door`);
  assert.deepEqual(wallPieces(WALL_LINES, DOORS).filter(p => p.door).map(p => p.door.id).sort(), DOORS.map(d => d.id).sort());
});

test('every room is reachable from the street without passing through a wall', () => {
  const street = { x: 0, z: -17 };
  for (const r of Object.values(ROOMS)) {
    const target = { x: (r.x0 + r.x1) / 2, z: (r.z0 + r.z1) / 2 };
    const legs = [street, ...grid.findPath(street, target)];
    assert.ok(Math.hypot(legs.at(-1).x - target.x, legs.at(-1).z - target.z) < 0.8, `${r.id} reached`);
    for (let i = 1; i < legs.length; i++) {
      assert.ok(!walls.some(w => segmentHitsRect(legs[i - 1].x, legs[i - 1].z, legs[i].x, legs[i].z, w, 0.25)), `${r.id} leg ${i}`);
    }
  }
});
