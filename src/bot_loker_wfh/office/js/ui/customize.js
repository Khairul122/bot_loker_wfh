// ---------- character customizer (name + colours), saved in localStorage ----------
import { me, myLook, LOOK_KEY } from '../characters/player.js';
import { $, closeFlyouts } from './dom.js';

const cu = { name: $('cuName'), skin: $('cuSkin'), hair: $('cuHair'), shirt: $('cuShirt'), pants: $('cuPants') };
Object.entries(cu).forEach(([k, input]) => { input.value = myLook[k]; input.oninput = () => {
  myLook[k] = input.value || 'Owner';
  try { localStorage.setItem(LOOK_KEY, JSON.stringify(myLook)); } catch {}
  me.setLook({ skin: myLook.skin, hair: myLook.hair, shirt: myLook.shirt, pants: myLook.pants }); me.name = myLook.name;
  $('meName').textContent = myLook.name; $('meFace').style.background = myLook.shirt;
}; });
$('meName').textContent = myLook.name; $('meFace').style.background = myLook.shirt;
$('bCustom').onclick = () => { const p = $('custom'); const open = !p.classList.contains('show'); if (open) closeFlyouts('custom'); p.classList.toggle('show', open); };
