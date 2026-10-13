// Proyek Freelance: five desks, a bean bag and a cork board (one note per interesting project)
import { box, sph, group, tag } from '../../core/factory.js';
import { rand, pick } from '../../core/util.js';
import { DESK_ROWS } from '../../domain/office-plan.js';
import { seats, solid, spot, dyn } from '../registry.js';

export default function build(g, d) {
  const { back, front } = DESK_ROWS;
  seats('freelance', [[-2.1, back], [0, back], [2.1, back], [-2.1, front], [0, front]], g, d.screen);
  const bag = sph(0.55, 0x6bb38a, 2.6, 0.32, 1.7, g); bag.scale.y = 0.6;
  tag(bag, { kind: 'spot', kindName: 'beanbag' }); solid(g, 2.6, 1.7, 1, 1);
  spot(g, { kind: 'beanbag', x: 2.6, z: 1.7, ry: 0, pose: 'floor', emo: '😌', energy: 7 });
  const board = group(2.4, 0, front + 0.5, g);
  for (const s of [-1, 1]) box(0.06, 2, 0.06, 0x8a6b55, s * 0.85, 1, 0, board);
  box(1.8, 1.2, 0.08, 0xc89a6c, 0, 1.4, 0, board);
  solid(g, 2.4, front + 0.5, 1.9, 0.4);
  const notes = [];
  for (let k = 0; k < 12; k++) { const n = box(0.24, 0.24, 0.02, pick([0xffe58a, 0xffb3c6, 0xb9f0c9, 0xbfe3f2]), -0.7 + (k % 6) * 0.28, 1.75 - Math.floor(k / 6) * 0.4, 0.05, board, { cast: false }); n.rotation.z = rand(-0.2, 0.2); n.visible = false; notes.push(n); }
  dyn.notes = notes;
}
