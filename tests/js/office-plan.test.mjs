import test from 'node:test';
import assert from 'node:assert/strict';
import { DOORS, OFFICE, PODS, ROOMS, wallPieces, wallRects, wallsCut } from '../../src/bot_loker_wfh/office/js/domain/office-plan.js';
import { createNavGrid, segmentHitsRect } from '../../src/bot_loker_wfh/office/js/domain/navgrid.js';

const walls = wallRects();
const grid = createNavGrid({ bounds: [-48, 48, -48, 48], walls, open: (x, z) => Math.hypot(x, z) < 46 });

test('the office is a single storey that stays clear of the homes and the island edge', () => {
  assert.ok(OFFICE.maxZ - OFFICE.minZ <= 32 && OFFICE.maxX - OFFICE.minX <= 38);
  assert.ok(OFFICE.minZ >= -14, 'clear of the housing street at z = -16.5');
  for (const x of [OFFICE.minX, OFFICE.maxX]) for (const z of [OFFICE.minZ, OFFICE.maxZ]) assert.ok(Math.hypot(x, z) < 40);
});

test('every room has a door and every door is cut into a wall', () => {
  for (const id of Object.keys(ROOMS)) assert.ok(DOORS.some(d => d.to.includes(id)), `${id} has a door`);
  assert.ok(DOORS.filter(d => d.to.includes('out')).length >= 2, 'more than one way out');
  const gaps = wallPieces().filter(p => p.door);
  assert.deepEqual(gaps.map(p => p.door.id).sort(), DOORS.map(d => d.id).sort());
});

test('each door joins the two spaces it names', () => {
  const at = p => Object.values(ROOMS).find(r => p.x > r.x0 && p.x < r.x1 && p.z > r.z0 && p.z < r.z1)?.id || 'out';
  for (const d of DOORS) {
    const off = d.axis === 'x' ? [{ x: d.x, z: d.z - 0.6 }, { x: d.x, z: d.z + 0.6 }] : [{ x: d.x - 0.6, z: d.z }, { x: d.x + 0.6, z: d.z }];
    assert.deepEqual(off.map(at).sort(), [...d.to].sort(), d.id);
  }
});

test('every room is reachable from the front yard without passing through a wall', () => {
  const yard = { x: 0, z: 26 };
  for (const r of Object.values(ROOMS)) {
    const target = { x: (r.x0 + r.x1) / 2, z: (r.z0 + r.z1) / 2 };
    const path = grid.findPath(yard, target);
    assert.ok(path, `${r.id} reachable`);
    const legs = [yard, ...path];
    for (let i = 1; i < legs.length; i++) {
      assert.ok(!walls.some(w => segmentHitsRect(legs[i - 1].x, legs[i - 1].z, legs[i].x, legs[i].z, w, 0.25)), `${r.id} leg ${i}`);
    }
  }
});

test('the back homes reach the office through a side door', () => {
  const path = grid.findPath({ x: -24.8, z: -16.5 }, { x: -15.2, z: 0.7 });
  assert.ok(path && path.length < 8);
});

test('division pods tile the work room', () => {
  const work = ROOMS.work;
  assert.equal(PODS.length, 6);
  assert.ok(Math.abs(PODS.reduce((a, p) => a + p.width, 0) - (work.x1 - work.x0)) < 1e-9);
});

test('walls drop when looking into the office from above, never in first person', () => {
  assert.equal(wallsCut({ fp: false, overview: true, inside: false }), true);
  assert.equal(wallsCut({ fp: false, overview: false, inside: true }), true);
  assert.equal(wallsCut({ fp: false, overview: false, inside: false }), false);
  assert.equal(wallsCut({ fp: true, overview: false, inside: true }), false);
});
