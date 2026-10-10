// ---------- lift panel: shown while the owner stands in the lift ----------
import { Snd } from '../core/sound.js';
import { V, DOOR_X, ROOF } from '../core/util.js';
import { DIVS } from '../buildings/divisions.js';
import { inLift } from '../world/navigation.js';
import { me } from '../characters/player.js';
import { $ } from './dom.js';

const LIFT_FLOORS = [{ icon: '🌿', name: 'Taman Atap', level: ROOF }, ...DIVS.map((d, i) => ({ icon: d.icon, name: d.name.replace('Divisi ', ''), level: i })).reverse()];
LIFT_FLOORS.forEach(f => {
  const b = document.createElement('button'); b.innerHTML = `<span>${f.icon}</span>${f.name}`; b.dataset.level = f.level;
  b.onclick = () => {
    if (me.ride) return;
    me.stop(); Snd.play('click');
    me.path = f.level === me.level ? [{ p: V(DOOR_X, 0) }] : [{ ride: f.level }, { p: V(DOOR_X, 0) }];
  };
  $('liftBtns').appendChild(b);
});
let liftShown = false, liftLevel = -1;
export function updateLiftPanel() {
  const show = inLift(me.pos) && !me.ride && !me.path.length;
  if (show !== liftShown) { liftShown = show; $('lift').classList.toggle('show', show); }
  if (show && liftLevel !== me.level) {
    liftLevel = me.level;
    $('liftBtns').querySelectorAll('button').forEach(b => b.classList.toggle('here', +b.dataset.level === me.level));
  }
}
