// ---------- character customizer (name + colours), saved in Supabase ----------
import { me, myLook } from '../characters/player.js';
import { $, closeFlyouts } from './dom.js';
import { savePref } from '../systems/prefs.js';

const cu = { name: $('cuName'), skin: $('cuSkin'), hair: $('cuHair'), shirt: $('cuShirt'), pants: $('cuPants') };
Object.entries(cu).forEach(([k, input]) => { input.value = myLook[k]; input.oninput = () => {
  myLook[k] = input.value || 'Owner';
  me.setLook({ skin: myLook.skin, hair: myLook.hair, shirt: myLook.shirt, pants: myLook.pants }); me.name = myLook.name;
  $('meName').textContent = myLook.name; $('meFace').style.background = myLook.shirt;
  savePref('look', JSON.stringify(myLook), 600);
}; });

// apply the look loaded from Supabase
export function applyLook(look) {
  Object.assign(myLook, look);
  Object.entries(cu).forEach(([k, input]) => { input.value = myLook[k]; });
  me.setLook({ skin: myLook.skin, hair: myLook.hair, shirt: myLook.shirt, pants: myLook.pants }); me.name = myLook.name;
  $('meName').textContent = myLook.name; $('meFace').style.background = myLook.shirt;
}
$('meName').textContent = myLook.name; $('meFace').style.background = myLook.shirt;
$('bCustom').onclick = () => { const p = $('custom'); const open = !p.classList.contains('show'); if (open) closeFlyouts('custom'); p.classList.toggle('show', open); };
