import test from 'node:test';
import assert from 'node:assert/strict';
import { createOfficeApi } from '../../src/bot_loker_wfh/office/js/infrastructure/office-api.js';

test('GET uses no-store and returns parsed response data', async () => {
  let request;
  const api = createOfficeApi(async (url, options) => {
    request = { url, options };
    return { ok: true, status: 200, json: async () => ({ live: true }) };
  }, '/office/');

  const response = await api.get('stats.json');

  assert.deepEqual(request, { url: '/office/stats.json', options: { cache: 'no-store' } });
  assert.deepEqual(response, { ok: true, status: 200, data: { live: true } });
});

test('POST serializes JSON only when a body is provided', async () => {
  const requests = [];
  const api = createOfficeApi(async (_url, options) => {
    requests.push(options);
    return { ok: true, status: 204, json: async () => { throw new Error('empty'); } };
  });

  assert.deepEqual(await api.post('auto', { enabled: true }), { ok: true, status: 204, data: {} });
  assert.deepEqual(await api.post('work/stop'), { ok: true, status: 204, data: {} });
  assert.deepEqual(requests, [
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"enabled":true}' },
    { method: 'POST', headers: {}, body: undefined },
  ]);
});

test('network failures resolve to the established offline response shape', async () => {
  const api = createOfficeApi(async () => { throw new Error('offline'); });
  assert.deepEqual(await api.get('stats.json'), { ok: false, status: 0, data: {} });
});
