// ---------- kantin menu: the owner orders food, alone or treating a colleague ----------
import { FOODS } from '../buildings/rooms/kantin.js';
import { playerEat } from '../ai/dining.js';
import { $ } from './dom.js';

let menuWith = null;
FOODS.forEach(f => {
  const b = document.createElement('button'); b.innerHTML = `${f.icon}<small>${f.name}</small>`;
  b.onclick = () => { closeMenu(); playerEat(f, menuWith); };
  $('menuBtns').appendChild(b);
});
export function openMenu(c = null) { menuWith = c; $('menuWith').textContent = c ? `· bareng ${c.name}` : ''; $('menu').classList.add('show'); }
export function closeMenu() { $('menu').classList.remove('show'); }
$('menuClose').onclick = () => { closeMenu(); menuWith = null; };
