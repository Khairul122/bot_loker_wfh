// ---------- stats polling: fetch stats.json, refresh moods, data-driven props and panels ----------
import { store, DEMO } from '../core/store.js';
import { clamp } from '../core/util.js';
import { derive, leadsBy } from '../data/stats.js';
import { dyn } from '../buildings/floor.js';
import { reportStack, drawKpi } from '../buildings/rooms/owner.js';
import { staff } from '../characters/team.js';
import { scheduleDeliveries } from '../ai/deliveries.js';
import { $, toast } from '../ui/dom.js';
import { perfOpen, renderPerf } from '../ui/perf.js';
import { reactToWork, renderAuto, renderBadge } from '../ui/inbox.js';

export function refreshPerf() {
  const d = derive();
  staff.forEach(c => { c.perfNow = c.def.perf(d); });
  const cards = dyn.cards || []; cards.forEach((c, i) => c.userData.on = i < clamp(Math.ceil(d.disc / 3) + 2, 2, 7));
  (dyn.letters || []).forEach((l, i) => l.visible = i < clamp(d.drafted, 1, 8));
  (dyn.planes || []).forEach((p, i) => p.visible = i < clamp(d.sent, 0, 8));
  (dyn.trophies || []).forEach((p, i) => p.visible = i < d.offer);
  (dyn.medals || []).forEach((p, i) => p.visible = i < d.interview);
  (dyn.notes || []).forEach((p, i) => p.visible = i < clamp(leadsBy().INTERESTED || 0, 0, 12));
  reportStack.forEach((p, i) => p.visible = i < Math.min(store.desk.tray, reportStack.length));
  drawKpi(staff);
  if (perfOpen) renderPerf();
}
export function refreshPanels() {
  $('liveDot').classList.toggle('live', store.live);
  $('liveDot').title = store.live ? 'Data langsung dari bot' : 'Data contoh (jalankan: python -m bot_loker_wfh office)';
  refreshPerf();
  reactToWork(); renderAuto(); renderBadge(); scheduleDeliveries();
}
export function applyStats(data) {
  const prev = store.live ? derive() : null;
  store.S = data; store.live = true;
  if (data.desk) store.desk = data.desk;
  if (prev) { const d = derive(); if (d.cand > prev.cand) toast(`🎉 ${d.cand - prev.cand} lowongan cocok baru!`); if (d.interview > prev.interview) toast('🎤 Ada panggilan interview baru!'); if (d.offer > prev.offer) toast('🏆 OFFER MASUK!!'); }
  refreshPanels();
}
export async function loadStats() {
  try {
    const r = await fetch('stats.json', { cache: 'no-store' });
    if (!r.ok) throw 0;
    applyStats(await r.json());
  } catch { store.live = false; store.S = DEMO; refreshPanels(); }
}
// poll faster while the team works on its own, so reactions show up promptly
export function poll() { setTimeout(async () => { await loadStats(); poll(); }, store.S.work?.auto ? 8000 : 60000); }
