// ---------- "go to" place list ----------
import { store } from '../core/store.js';
import { ROOF } from '../core/util.js';
import { DIVS, OWNER } from '../buildings/divisions.js';
import { me } from '../characters/player.js';
import { useSpot, sitOwner, goHouse } from '../ai/owner-actions.js';
import { $ } from './dom.js';
import { endChat } from './card.js';

const PLACES = [
  { icon: '🌳', name: 'Taman', go: () => me.goTo(0, -25, 8) },
  { icon: '🎮', name: 'Arena Bermain', go: () => me.goTo(0, 24, 0) },
  { icon: '☕', name: 'Kafe Santai', go: () => useSpot('kafe') },
  { hr: 1 },
  { icon: '🏠', name: 'Rumahku', go: () => goHouse(me.home) },
  { icon: '🏘️', name: 'Komplek Rumah', go: () => me.goTo(0, 0, -16.5) },
  { hr: 1 },
  ...DIVS.map((d, i) => ({ icon: d.icon, name: d.name.replace('Divisi ', ''), go: () => i === OWNER ? sitOwner(false) : me.goTo(i, 2, 4) })),
  { icon: '🌿', name: 'Taman Atap', go: () => me.goTo(ROOF, 0, 1) },
];
const narrow = () => innerWidth <= 760;
function setNav(open) { $('nav').classList.toggle('open', open); $('bNav').setAttribute('aria-expanded', open); }
setNav(!narrow());
$('bNav').onclick = () => setNav(!$('nav').classList.contains('open'));
PLACES.forEach(p => {
  if (p.hr) { $('nav').appendChild(document.createElement('hr')); return; }
  const b = document.createElement('button'); b.innerHTML = `<i>${p.icon}</i><span>${p.name}</span>`; b.title = p.name;
  b.onclick = () => { endChat(); store.overview = false; p.go(); if (narrow()) setNav(false); }; $('nav').appendChild(b);
});
$('bOver').onclick = () => { store.overview = !store.overview; endChat(); };
