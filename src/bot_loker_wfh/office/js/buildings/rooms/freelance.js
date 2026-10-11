// level 6: bean bags and a cork board (one note per interesting project)
import { box, sph } from '../../core/factory.js';
import { rand, pick } from '../../core/util.js';
import { plant } from '../../world/props.js';
import { seats, dyn } from '../floor.js';

export default function build(g, d) {
  // four desks for the team, the manager's own desk at the head of the room
  seats('freelance', [[-5, -3], [-1.2, -3], [-5, 1.2], [-1.2, 1.2], [4, -3]], g, d.screen);
  for (const [x, z, c] of [[2, 2, 0xef8a6b], [4, 3.5, 0x6bb38a], [6, 2, 0x7aa6d8]]) { const b = sph(0.7, c, x, 0.45, z, g); b.scale.y = 0.65; }
  box(4, 2.4, 0.1, 0xc89a6c, 4, 2, -5.7, g); // cork board
  const notes = [];
  for (let k = 0; k < 12; k++) { const n = box(0.5, 0.5, 0.03, pick([0xffe58a, 0xffb3c6, 0xb9f0c9, 0xbfe3f2]), 2.5 + (k % 6) * 0.6, 2.6 - Math.floor(k / 6) * 0.8, -5.62, g, { cast: false }); n.rotation.z = rand(-0.2, 0.2); n.visible = false; notes.push(n); }
  dyn.notes = notes;
  plant(-8, 5, g, 1.3);
}
