// ---------- "go to" place list ----------
import { store } from '../core/store.js';
import { PODS } from '../domain/office-plan.js';
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
  { icon: '🏘️', name: 'Rumah Susun', go: () => me.goTo(0, 0, -23) },
  { hr: 1 },
  ...DIVS.map(d => ({
    icon: d.icon,
    name: d.name.replace('Divisi ', ''),
    manager: EMPLOYEES.find(employee => employee.id === d.manager)?.name || d.manager,
    go: () => { const pod = PODS.find(p => p.id === d.id); pod ? me.goTo(0, pod.x, pod.z) : useSpot('sofa'); },
  })),
  { icon: '👑', name: 'Ruang Owner', go: () => sitOwner(false) },
  { icon: '💬', name: 'Ruang Rapat', go: () => useSpot('rapat') },
  { icon: '🍜', name: 'Kantin', go: () => useSpot('kantin') },
  { icon: '🚻', name: 'Toilet', go: () => useSpot('toilet') },
  { icon: '🛋️', name: 'Ruang Santai', go: () => useSpot('foosball') },
  { icon: '📚', name: 'Ruang Fokus', go: () => useSpot('baca') },
  { icon: '🌿', name: 'Teras Taman', go: () => useSpot('hammock') },
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

// toolbar buttons are icons only: a click shows the name under the button for a moment
const toolName = document.createElement('div'); toolName.id = 'toolName'; toolName.setAttribute('aria-hidden', 'true'); document.body.append(toolName);
let toolNameTimer = 0;
$('tools').addEventListener('click', e => {
  const b = e.target.closest('.tbtn[data-name]'); if (!b) return;
  const r = b.getBoundingClientRect();
  toolName.textContent = b.dataset.name;
  toolName.style.left = r.left + r.width / 2 + 'px'; toolName.style.top = r.bottom + 6 + 'px';
  toolName.classList.add('show');
  clearTimeout(toolNameTimer); toolNameTimer = setTimeout(() => toolName.classList.remove('show'), 1400);
});
