// ---------- dollhouse cut: everything above the owner's floor is left out, house roofs lift ----------
import { store } from '../core/store.js';
import { FH, ROOF } from '../core/util.js';
import { floors } from '../buildings/floor.js';
import { shaft, landings } from '../buildings/tower.js';
import { roof } from '../buildings/rooftop.js';
import { houses } from '../buildings/houses.js';
import { inTower, inR } from '../world/navigation.js';
import { me } from '../characters/player.js';
import { chars } from '../characters/char.js';

// A floor above the owner is not drawn at all (no see-through ghosts of desks and signs).
// userData.faded stays as the flag pointer.js reads so clicks reach the owner's floor.
function setCut(g, cut) {
  if (!!g.userData.faded === cut) return;
  g.userData.faded = cut;
  g.visible = !cut;
}

export function updateCutaway() {
  const inside = me.level > 0 || inTower(me.pos);
  const lvl = store.overview || store.fp || !inside ? 99 : Math.max(me.level, Math.round(me.y / FH));
  floors.forEach((g, i) => setCut(g, i > lvl));
  setCut(roof, ROOF > lvl);
  // the glass lift shaft ends at the ceiling of the owner's floor, with the landings above it
  const top = lvl >= ROOF ? ROOF * FH + 1 : (lvl + 1) * FH;
  shaft.scale.y = top / (ROOF * FH + 1);
  shaft.position.y = top / 2 - 0.4;
  landings.forEach((m, i) => { m.visible = i <= lvl; });
  // people and their bubbles on floors above the owner disappear with those floors
  for (const c of chars) c.p.root.visible = c.level <= lvl;
  // lift the roof off the house the owner is standing in
  for (const h of houses) h.roof.visible = h.chimney.visible = store.fp || me.level !== 0 || !inR(me.pos.x, me.pos.z, h.box, 0);
}
