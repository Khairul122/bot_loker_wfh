// ---------- floor see-through: floors above the owner fade instead of vanishing; house roofs lift ----------
import { store } from '../core/store.js';
import { FH, ROOF } from '../core/util.js';
import { floors } from '../buildings/floor.js';
import { roof } from '../buildings/rooftop.js';
import { houses } from '../buildings/houses.js';
import { inTower, inR } from '../world/navigation.js';
import { me } from '../characters/player.js';
import { chars } from '../characters/char.js';

// ponytail: faded clones copy emissive at swap time only; a day/night flip while faded shows on the next swap
// floors above the owner are almost glass: just a faint outline of the building, nothing to read through
const FADE_OPACITY = 0.06;
const fadedOf = new Map();
function faded(m) {
  let f = fadedOf.get(m);
  if (!f) { f = m.clone(); f.transparent = true; f.opacity = FADE_OPACITY; f.depthWrite = false; fadedOf.set(m, f); }
  if (m.emissive) f.emissiveIntensity = m.emissiveIntensity;
  return f;
}
function setFaded(g, on) {
  if (!!g.userData.faded === on) return;
  g.userData.faded = on; // pointer.js skips faded floors so clicks reach the owner's floor
  g.traverse(o => {
    if (!o.isMesh) return;
    if (on) { o.userData.mat0 = o.material; o.userData.cast0 = o.castShadow; o.material = faded(o.material); o.castShadow = false; }
    else if (o.userData.mat0) { o.material = o.userData.mat0; o.castShadow = o.userData.cast0; }
  });
}

export function updateCutaway() {
  const inside = me.level > 0 || inTower(me.pos);
  const lvl = store.overview || store.fp || !inside ? 99 : Math.max(me.level, Math.round(me.y / FH));
  floors.forEach((g, i) => setFaded(g, i > lvl));
  setFaded(roof, ROOF > lvl);
  // people and their bubbles on floors above the owner disappear with those floors
  for (const c of chars) c.p.root.visible = c.level <= lvl;
  // lift the roof off the house the owner is standing in
  for (const h of houses) h.roof.visible = h.chimney.visible = store.fp || me.level !== 0 || !inR(me.pos.x, me.pos.z, h.box, 0);
}
