import test from 'node:test';
import assert from 'node:assert/strict';
import { createNavGrid, segmentHitsRect } from '../../src/bot_loker_wfh/office/js/domain/navgrid.js';

// a 10 m room around the origin with one 2 m doorway in its south wall (z = 5, x in [-1, 1])
const room = [
  [-5.15, 5.15, -5.15, -4.85], [-5.15, -4.85, -5, 5], [4.85, 5.15, -5, 5],
  [-5.15, -1, 4.85, 5.15], [1, 5.15, 4.85, 5.15],
];
const bounds = [-12, 12, -12, 12];
const crossesWall = (pts, walls) => pts.slice(1).some((p, i) =>
  walls.some(r => segmentHitsRect(pts[i].x, pts[i].z, p.x, p.z, r, 0.25)));

test('a route into a walled room goes through its doorway, never through a wall', () => {
  const grid = createNavGrid({ bounds, walls: room });
  const from = { x: 0, z: -9 }, to = { x: 0, z: 0 };
  const path = grid.findPath(from, to);

  assert.ok(path, 'route exists');
  assert.equal(crossesWall([from, ...path], room), false);
  assert.ok(path.some(p => p.z > 5.5), 'walks around to the south door');
  assert.ok(Math.hypot(path.at(-1).x, path.at(-1).z) < 0.5, 'ends at the target');
});

test('a sealed room is never entered and furniture is walked around', () => {
  const sealed = [...room, [-1, 1, 4.85, 5.15]];
  const start = { x: 0, z: -9 }, blockedPath = createNavGrid({ bounds, walls: sealed }).findPath(start, { x: 0, z: 0 }, { exact: true });
  assert.equal(crossesWall([start, ...blockedPath], sealed), false);
  assert.ok(blockedPath.at(-1).z < -5.15, 'stops outside the sealed room');

  const table = [-3, 3, -0.5, 0.5];
  const grid = createNavGrid({ bounds, walls: room, solids: [table] });
  const from = { x: 0, z: -3 }, path = grid.findPath(from, { x: 0, z: 3 });
  assert.ok(path);
  assert.equal(crossesWall([from, ...path], [table]), false);
});

test('a target hugging a wall snaps to a free cell on its own side', () => {
  const grid = createNavGrid({ bounds, walls: room });
  const inside = grid.nearestFree({ x: 0, z: -4.75 });
  assert.ok(inside.z > -4.85, 'stays inside the room');
  const outside = grid.nearestFree({ x: 0, z: -5.25 });
  assert.ok(outside.z < -5.15, 'stays outside the room');
});

test('a seat boxed in by furniture is reached from the free side it faces', () => {
  // a sofa against the west wall facing east, a table close in front, bean bags walling off the north
  const sofa = [-4.85, -3.95, -1.2, 1.2], table = [-2.6, -1.9, -0.6, 0.6], bags = [-4.85, -1, 1.6, 2.6];
  const grid = createNavGrid({ bounds, walls: room, solids: [sofa, table, bags] });
  const seat = { x: -4.3, z: 0 }, from = { x: 3, z: 8 };
  const path = grid.findPath(from, seat, { exact: true, prefer: { x: 1, z: 0 } });
  assert.equal(crossesWall([from, ...path], room), false);
  assert.deepEqual(path.at(-1), seat);
  const before = path.at(-2);
  assert.ok(before.x > seat.x, 'arrives from the front of the sofa');
});
