// Penulisan: a reading sofa by the bookshelf, floating letters (one per draft)
import { box, tag, animated } from '../../core/factory.js';
import { shelf, sofa } from '../../world/props.js';
import { DESK_ROWS } from '../../domain/office-plan.js';
import { seats, solid, spot, dyn } from '../registry.js';

export default function build(g, d) {
  const { back, front } = DESK_ROWS;
  seats('tulis', [[-1.05, back], [1.05, back]], g, d.screen);
  shelf(-1.5, front + 0.3, 0, g); solid(g, -1.5, front + 0.3, 2, 0.5);
  tag(sofa(1.4, front, 0, g, 0xb48ad8), { kind: 'spot', kindName: 'sofa' }); solid(g, 1.4, front, 2.4, 0.9);
  spot(g, { kind: 'sofa', x: 1.4, z: front + 0.05, ry: 0, pose: 'sit', emo: '📚', energy: 6 });
  const letters = [];
  for (let k = 0; k < 8; k++) { const l = box(0.5, 0.02, 0.35, 0xfffaf0, 0, 2.2, front, g, { cast: false }); l.userData.o = k; letters.push(l); }
  dyn.letters = letters;
  animated.push(t => letters.forEach(l => {
    const o = l.userData.o;
    l.position.set(Math.sin(t * 0.4 + o) * 2, 2.2 + Math.sin(t * 1.3 + o) * 0.3, front - 1.2 + Math.cos(t * 0.6 + o) * 0.6);
    l.rotation.y = t * 0.5 + o;
  }));
}
