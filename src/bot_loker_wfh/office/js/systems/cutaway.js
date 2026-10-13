// ---------- dollhouse cut: walls drop to waist height and the roof lifts on the building the owner is in ----------
import { store } from '../core/store.js';
import { office } from '../buildings/office.js';
import { rusun } from '../buildings/houses.js';
import { inOffice } from '../world/navigation.js';
import { wallsCut } from '../domain/office-plan.js';
import { me } from '../characters/player.js';

const buildings = [{ b: office, inside: inOffice, on: null }, { b: rusun, inside: rusun.inside, on: null }];
function setCut(entry, on) {
  if (on === entry.on) return;
  entry.on = on;
  const { b } = entry;
  for (const o of b.cut) o.scale.y = on ? b.cutScale : 1;
  // userData.faded is what pointer.js reads to skip hidden meshes
  for (const o of b.upper) { o.visible = !on; o.userData.faded = on; }
  b.roof.visible = !on; b.roof.userData.faded = on;
}

export function updateCutaway() {
  for (const e of buildings) setCut(e, wallsCut({ fp: store.fp, overview: store.overview, inside: e.inside(me.pos) }));
}
