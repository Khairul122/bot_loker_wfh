import test from 'node:test';
import assert from 'node:assert/strict';
import { advancePosition } from '../../src/bot_loker_wfh/office/js/domain/movement.js';

test('walking cannot cross a wall outside its doorway and can slide into the doorway', () => {
  const wallZ = 6;
  const doorwayHalfWidth = 2.1;
  const canMove = (from, to) => {
    const crossesWall = (from.z < wallZ && to.z >= wallZ) || (from.z >= wallZ && to.z < wallZ);
    if (!crossesWall) return true;
    const t = (wallZ - from.z) / (to.z - from.z);
    const crossingX = from.x + (to.x - from.x) * t;
    return Math.abs(crossingX) <= doorwayHalfWidth;
  };

  const end = advancePosition({ x: 8, z: 8 }, { x: 0, z: 2 }, 10, canMove);

  assert.ok(Math.abs(end.x) <= doorwayHalfWidth, 'crossing uses the 4.2m opening');
  assert.ok(end.z < wallZ);
});

test('walking remains collision constrained even when a frame requests a long movement step', () => {
  const canMove = (from, to) => !(from.x < 0 && to.x >= 0 && from.z > 1);

  const end = advancePosition({ x: -2, z: 2 }, { x: 2, z: 2 }, 4, canMove);

  assert.ok(end.x < 0, 'substeps cannot tunnel through the wall');
});
