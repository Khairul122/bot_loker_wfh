import test from 'node:test';
import assert from 'node:assert/strict';
import { adjustMoodForEnergy, updateEnergy } from '../../src/bot_loker_wfh/office/js/domain/employee-state.js';

const ladder = ['ngantuk', 'lelah', 'fokus', 'senang', 'semangat'];

test('work drains energy and rest restores it within bounds', () => {
  assert.ok(updateEnergy(80, 'work', 60) < 80);
  assert.ok(updateEnergy(20, 'break', 30) > 20);
  assert.equal(updateEnergy(99, 'sleep', 60), 100);
  assert.equal(updateEnergy(0, 'work', 60), 0);
});

test('energy shifts employee expression without erasing sadness', () => {
  assert.equal(adjustMoodForEnergy('senang', 10, ladder), 'lelah');
  assert.equal(adjustMoodForEnergy('senang', 30, ladder), 'fokus');
  assert.equal(adjustMoodForEnergy('fokus', 98, ladder), 'senang');
  assert.equal(adjustMoodForEnergy('sedih', 100, ladder), 'sedih');
});
