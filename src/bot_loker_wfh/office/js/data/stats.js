// numbers every employee's performance is computed from (store.S comes from stats.json)
import { store } from '../core/store.js';
import { clamp } from '../core/util.js';

export const sum = o => Object.values(o || {}).reduce((a, b) => a + (typeof b === 'number' ? b : sum(b)), 0);
export const r01 = v => clamp(v, 0, 1);
export function derive() {
  const S = store.S;
  const A = k => (S.applications || {})[k] || 0;
  const jobs = S.jobs || {};
  const cand = Object.values(jobs).reduce((a, j) => a + (j.CANDIDATE || 0), 0);
  const disc = Object.values(jobs).reduce((a, j) => a + (j.DISCOVERED || 0), 0);
  const filtered = Object.values(jobs).reduce((a, j) => a + (j.FILTERED_OUT || 0), 0);
  const total = sum(jobs);
  const sent = ['SUBMITTED', 'VIEWED', 'INTERVIEW', 'OFFER', 'REJECTED_BY_COMPANY', 'NO_RESPONSE'].reduce((a, k) => a + A(k), 0);
  const responded = ['VIEWED', 'INTERVIEW', 'OFFER', 'REJECTED_BY_COMPANY'].reduce((a, k) => a + A(k), 0);
  return { A, jobs, cand, disc, filtered, total, processed: total - disc, sent, responded, interview: A('INTERVIEW') + A('OFFER'), offer: A('OFFER'), drafted: sum(S.applications), pending: A('PENDING_APPROVAL') + A('DRAFT_READY'), failed: A('SUBMIT_FAILED') };
}
export const leadsBy = src => src ? (store.S.leads || {})[src] || {} : Object.values(store.S.leads || {}).reduce((a, o) => { for (const k in o) a[k] = (a[k] || 0) + o[k]; return a; }, {});
