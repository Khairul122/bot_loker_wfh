import test from 'node:test';
import assert from 'node:assert/strict';

import { store } from '../../src/bot_loker_wfh/office/js/core/store.js';
import { overviewCameraPose, ownerCameraPose } from '../../src/bot_loker_wfh/office/js/domain/owner-camera.js';

test('a page refresh starts in owner-follow mode, not building overview', () => {
  assert.equal(store.overview, false);
});

test('owner camera framing is centered on the restored owner position', () => {
  assert.deepEqual(ownerCameraPose({ x: 12, y: 8, z: -4 }), {
    position: { x: 34, y: 26, z: 24 },
    target: { x: 12, y: 9.2, z: -4 },
  });
});

test('overview framing is wide enough to include the front campus and homes', () => {
  const pose = overviewCameraPose();
  const distance = Math.hypot(
    pose.position.x - pose.target.x,
    pose.position.y - pose.target.y,
    pose.position.z - pose.target.z,
  );

  assert.ok(distance > 100 && distance < 120);
  assert.deepEqual(pose.target, { x: 3, y: 4, z: 0 });
});
