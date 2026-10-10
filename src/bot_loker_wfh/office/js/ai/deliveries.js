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
import { post, toast } from '../ui/dom.js';
import { loadStats } from '../systems/sync.js';
import { goBack } from './routine.js';

const delivering = new Set();
export function scheduleDeliveries() {
  if (!store.live) return;
  for (const r of store.desk.undelivered) {
    const slot = DELIVER_AT.find(p => !p.by); if (!slot) return;
    const c = byId(r.employee);
    if (delivering.has(r.id) || !c || ['report', 'chat'].includes(c.state) || c.ride) continue;
    deliver(c, r, slot);
  }
}
function deliver(c, r, slot) {
  delivering.add(r.id); slot.by = c;
  c.state = 'report'; c.afterBreak = null; c.drop();
  c.carry(new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.03, 0.3), mat(0xffffff)));
  c.showEmo('📋'); say(c, pick(['Antar laporan ke bos dulu 📋', 'Laporanku sudah jadi! 📋']), 3);
  const done = ok => { delivering.delete(r.id); slot.by = null; c.drop(); goBack(c); if (ok) loadStats(); };
  c.goTo(OWNER, slot.x, slot.z, () => {
    c.targetRy = Math.PI; c.doEmote('give', 1.8);
    say(c, `Bos, laporanku: ${r.lines[0] || 'beres semua'} 📋`, 5);
    if (me.level === OWNER) { me.face(c.pos.x, c.pos.z); me.doEmote('nod', 1.5); }
    setTimeout(async () => {
      const res = await post(`reports/${encodeURIComponent(r.id)}/delivered`);
      Snd.play('pop'); if (res.ok) toast(`📋 ${c.name} menaruh laporan di meja owner`);
      done(res.ok);
    }, 1700);
  });
}
