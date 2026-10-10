// ---------- floor visibility: hide the floors above the owner, lift house roofs ----------
import { store } from '../core/store.js';
import { FH, ROOF } from '../core/util.js';
import { floors } from '../buildings/floor.js';
import { roof } from '../buildings/rooftop.js';
import { houses } from '../buildings/houses.js';
import { inTower, inR } from '../world/navigation.js';
import { chars } from '../characters/char.js';
import { me } from '../characters/player.js';

export function updateCutaway() {
  const inside = me.level > 0 || inTower(me.pos);
  const lvl = store.overview || store.fp || !inside ? 99 : Math.max(me.level, Math.round(me.y / FH));
  floors.forEach((g, i) => g.visible = i <= lvl);
  roof.visible = ROOF <= lvl;
  for (const c of chars) c.p.root.visible = !(c.level > lvl && (c.level > 0 || inTower(c.pos))) || !!c.ride;
  // lift the roof off the house the owner is standing in
  for (const h of houses) h.roof.visible = h.chimney.visible = store.fp || me.level !== 0 || !inR(me.pos.x, me.pos.z, h.box, 0);
}
