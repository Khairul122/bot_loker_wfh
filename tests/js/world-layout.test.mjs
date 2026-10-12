import test from 'node:test';
import assert from 'node:assert/strict';
import { placeAnnexContents } from '../../src/bot_loker_wfh/office/js/domain/world-layout.js';

test('annex placement translates spots, interior routes, and private-room access together', () => {
  const spots = [
    { level: 9, x: 2, z: -1, via: [{ x: 1, z: 0 }], box: [-2, 2, -3, 3] },
    { level: 9, x: -1, z: 2 },
  ];
  const walls = [[-2, 2, -3, -2, 9]];

  placeAnnexContents(spots, walls, { x: 20, z: 16, level: 0, ownerOnly: true });

  assert.deepEqual(spots[0], {
    level: 0, x: 22, z: 15,
    via: [{ x: 20, z: 23.2 }, { x: 20, z: 21.2 }, { x: 21, z: 16 }],
    box: [18, 22, 13, 19],
    ownerOnly: true,
  });
  assert.deepEqual(spots[1], {
    level: 0, x: 19, z: 18,
    via: [{ x: 20, z: 23.2 }, { x: 20, z: 21.2 }],
    box: [11, 29, 10, 22],
    ownerOnly: true,
  });
  assert.deepEqual(walls, [[18, 22, 13, 14, 0]]);
});
