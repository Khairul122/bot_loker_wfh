// ---------- dollhouse cut: office walls drop to waist height and its roof lifts, house roofs lift ----------
import { store } from '../core/store.js';
import { office } from '../buildings/office.js';
import { houses } from '../buildings/houses.js';
import { inOffice, inR } from '../world/navigation.js';
import { wallsCut } from '../domain/office-plan.js';
import { me } from '../characters/player.js';

let cutNow = null;
function setCut(on) {
  if (on === cutNow) return;
  cutNow = on;
  for (const o of office.cut) o.scale.y = on ? office.cutScale : 1;
  // userData.faded is what pointer.js reads to skip hidden meshes
  for (const o of office.upper) { o.visible = !on; o.userData.faded = on; }
  office.roof.visible = !on; office.roof.userData.faded = on;
}

export function updateCutaway() {
  setCut(wallsCut({ fp: store.fp, overview: store.overview, inside: inOffice(me.pos) }));
  // lift the roof off the house the owner is standing in
  for (const h of houses) h.roof.visible = h.chimney.visible = store.fp || !inR(me.pos.x, me.pos.z, h.box, 0);
}
