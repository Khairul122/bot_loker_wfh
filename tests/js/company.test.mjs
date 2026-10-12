import test from 'node:test';
import assert from 'node:assert/strict';
import { DIVISIONS, EMPLOYEES, MANAGERS, MAX_FLOORS } from '../../src/bot_loker_wfh/office/js/domain/company.js';

test('office company metadata fits the approved seven-floor plan', () => {
  assert.equal(MAX_FLOORS, 7);
  assert.equal(DIVISIONS.length, 7);
  assert.deepEqual(DIVISIONS.map(({ floor }) => floor), [0, 1, 2, 3, 4, 5, 6]);
});

test('every division has its approved manager and every employee has a division', () => {
  assert.deepEqual(MANAGERS, {
    lobi: 'tegar',
    cari: 'reno',
    seleksi: 'sari',
    tulis: 'cora',
    lamar: 'subi',
    pantau: 'tara',
    freelance: 'mira',
  });
  assert.equal(EMPLOYEES.length, 20);
  assert.equal(EMPLOYEES.every(({ division }) => MANAGERS[division]), true);
});
