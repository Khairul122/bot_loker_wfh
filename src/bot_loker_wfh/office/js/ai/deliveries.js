// ---------- reports walked to the owner's desk ----------
import * as THREE from 'three';
import { mat } from '../core/factory.js';
import { Snd } from '../core/sound.js';
import { store } from '../core/store.js';
import { pick } from '../core/util.js';
import { OWNER } from '../buildings/divisions.js';
import { DELIVER_AT } from '../buildings/rooms/owner.js';
import { me } from '../characters/player.js';
import { byId } from '../characters/team.js';
import { say } from '../fx/bubbles.js';
import { toast } from '../ui/dom.js';
import { post } from '../infrastructure/office-api.js';
import { loadStats } from '../systems/sync.js';
import { goBack } from './routine.js';

const delivering = new Set();
export function scheduleDeliveries() {
  if (!store.live) return;
  for (const r of store.desk.undelivered) {
    if (delivering.has(r.id)) continue;
    const c = byId(r.employee);
    if (!c || ['report', 'chat'].includes(c.state)) continue;
    const manager = r.to === 'manager' ? byId(r.manager) : null;
    if (r.to === 'manager' && !manager) continue;
    const slot = manager ? null : DELIVER_AT.find(p => !p.by);
    if (!manager && !slot) return;
    deliver(c, r, slot, manager);
  }
}
function deliver(c, r, slot, manager) {
  delivering.add(r.id); if (slot) slot.by = c;
  c.state = 'report'; c.afterBreak = null; c.drop();
  c.carry(new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.03, 0.3), mat(0xffffff)));
  c.showEmo('📋'); say(c, manager ? `Antar laporan ke ${manager.name} 📋` : pick(['Antar laporan ke bos dulu 📋', 'Laporanku sudah jadi! 📋']), 3);
  const done = ok => { delivering.delete(r.id); if (slot) slot.by = null; c.drop(); goBack(c); if (ok) loadStats(); };
  const target = manager ? manager.seat : slot;
  c.goTo(manager?.level ?? OWNER, target.x, target.z, () => {
    if (manager) c.face(manager.pos.x, manager.pos.z);
    else c.targetRy = Math.PI;
    c.doEmote('give', 1.8);
    say(c, manager
      ? `${manager.name}, ini laporan harian divisi: ${r.lines[0] || 'beres semua'} 📋`
      : `Bos, laporanku: ${r.lines[0] || 'beres semua'} 📋`, 5);
    if (!manager && me.spot?.kind === 'owner') { me.face(c.pos.x, c.pos.z); me.doEmote('nod', 1.5); }
    setTimeout(async () => {
      const endpoint = manager ? 'handed' : 'delivered';
      const res = await post(`reports/${encodeURIComponent(r.id)}/${endpoint}`);
      Snd.play('pop'); if (res.ok) toast(manager
        ? `📋 ${c.name} menyerahkan laporan ke ${manager.name}`
        : `📋 ${c.name} menaruh laporan di meja owner`);
      done(res.ok);
    }, 1700);
  });
}
