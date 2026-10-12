import test from 'node:test';
import assert from 'node:assert/strict';
import { CANTEEN_ORDER_OFFSETS, SUPPORT_BUILDING_SITES } from '../../src/bot_loker_wfh/office/js/domain/campus-layout.js';

const FOOTPRINT = { width: 18, depth: 12 };
const WORLD_RADIUS = 47;
const houses = [-21, -31, -41].flatMap(z =>
  Array.from({ length: 9 }, (_, column) => ({ x: -24.8 + column * 6.2, z })),
);

test('support pavilions occupy clear, walkable campus sites instead of the housing rows', () => {
  const sites = Object.entries(SUPPORT_BUILDING_SITES);
  assert.equal(sites.length, 3);

  for (let i = 0; i < sites.length; i++) {
    const [name, site] = sites[i];
    const bounds = [site.x - FOOTPRINT.width / 2, site.x + FOOTPRINT.width / 2,
      site.z - FOOTPRINT.depth / 2, site.z + FOOTPRINT.depth / 2];
    const farthestCorner = Math.max(
      ...[bounds[0], bounds[1]].flatMap(x => [bounds[2], bounds[3]].map(z => Math.hypot(x, z))),
    );

    assert.ok(farthestCorner < WORLD_RADIUS, `${name} stays inside the walkable island`);
    assert.ok(houses.every(house =>
      Math.abs(site.x - house.x) >= (FOOTPRINT.width + 5.2) / 2 ||
      Math.abs(site.z - house.z) >= (FOOTPRINT.depth + 5.2) / 2,
    ), `${name} does not overlap a home`);

    for (const [, other] of sites.slice(i + 1)) {
      assert.ok(Math.abs(site.x - other.x) >= FOOTPRINT.width ||
        Math.abs(site.z - other.z) >= FOOTPRINT.depth, `${name} does not overlap another pavilion`);
    }
  }
});

test('canteen queue positions resolve inside the canteen pavilion', () => {
  const site = SUPPORT_BUILDING_SITES.canteen;
  const bounds = [site.x - FOOTPRINT.width / 2, site.x + FOOTPRINT.width / 2,
    site.z - FOOTPRINT.depth / 2, site.z + FOOTPRINT.depth / 2];

  assert.ok(CANTEEN_ORDER_OFFSETS.length > 0);
  for (const offset of CANTEEN_ORDER_OFFSETS) {
    const x = site.x + offset.x, z = site.z + offset.z;
    assert.ok(x > bounds[0] && x < bounds[1]);
    assert.ok(z > bounds[2] && z < bounds[3]);
  }
});
