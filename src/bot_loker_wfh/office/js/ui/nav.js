// ---------- "go to" place list ----------
import { store } from '../core/store.js';
import { ROOF } from '../core/util.js';
import { DIVS } from '../buildings/divisions.js';
import { EMPLOYEES } from '../domain/company.js';
import { me } from '../characters/player.js';
import { useSpot, sitOwner, goHouse } from '../ai/owner-actions.js';
import { focusOwnerCamera, focusOverviewCamera, setFP } from '../systems/camera.js';
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
  ...DIVS.map(d => ({
    icon: d.icon,
    name: d.name.replace('Divisi ', ''),
    manager: EMPLOYEES.find(employee => employee.id === d.manager)?.name || d.manager,
    go: () => me.goTo(d.floor, 2, 4),
  })),
  { icon: '👑', name: 'Ruang Owner', go: () => sitOwner(false) },
  { icon: '💬', name: 'Ruang Rapat', go: () => useSpot('rapat') },
  { icon: '🍜', name: 'Kantin', go: () => useSpot('kantin') },
  { icon: '🚻', name: 'Kamar Mandi', go: () => useSpot('toilet') },
  { icon: '🌿', name: 'Taman Atap', go: () => me.goTo(ROOF, 0, 1) },
];
const narrow = () => innerWidth <= 760;
function setNav(open) { $('nav').classList.toggle('open', open); $('bNav').setAttribute('aria-expanded', open); }
setNav(!narrow());
$('bOver').classList.toggle('on', store.overview);
$('bNav').onclick = () => setNav(!$('nav').classList.contains('open'));
PLACES.forEach(p => {
  if (p.hr) { $('nav').appendChild(document.createElement('hr')); return; }
  const b = document.createElement('button');
  const icon = document.createElement('i'); icon.textContent = p.icon;
  const label = document.createElement('span'); label.className = 'place-label'; label.textContent = p.name;
  if (p.manager) {
    const manager = document.createElement('small'); manager.className = 'place-manager';
    manager.textContent = `Manager: ${p.manager}`;
    label.append(manager);
  }
  b.append(icon, label);
  b.title = p.manager ? `${p.name}, manager ${p.manager}` : p.name;
  b.setAttribute('aria-label', b.title);
  b.onclick = () => { endChat(); store.overview = false; p.go(); if (narrow()) setNav(false); }; $('nav').appendChild(b);
});
$('bOver').onclick = () => {
  const overview = !store.overview;
  if (store.fp) setFP(false);
  store.overview = overview;
  (overview ? focusOverviewCamera : focusOwnerCamera)();
  $('bOver').classList.toggle('on', overview);
  endChat();
};
