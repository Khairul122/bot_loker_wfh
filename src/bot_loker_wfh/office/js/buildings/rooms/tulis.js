// level 3: writers' room, bookshelves, floating letters (one per draft)
import { box, tag, animated } from '../../core/factory.js';
import { shelf, rug, sofa, plant } from '../../world/props.js';
import { seats, dyn } from '../floor.js';

export default function build(g, d) {
  seats('tulis', [[-5, -3], [-1.2, -3]], g, d.screen);
  shelf(5, -4.6, 0, g); shelf(7.4, -4.6, 0, g); rug(-5, 3.5, 2, 0xf2b84b, g);
  tag(sofa(-5, 3.5, 0, g, 0xb48ad8), { kind: 'spot', kindName: 'sofa' });
  const letters = [];
  for (let k = 0; k < 8; k++) { const l = box(0.5, 0.02, 0.35, 0xfffaf0, 2 + k * 0.7, 2, 1, g, { cast: false }); l.userData.o = k; letters.push(l); }
  dyn.letters = letters;
  animated.push(t => letters.forEach(l => { const o = l.userData.o; l.position.y = 2 + Math.sin(t * 1.3 + o) * 0.4; l.rotation.y = t * 0.5 + o; l.position.z = 1 + Math.cos(t * 0.6 + o) * 1.2; }));
  plant(8, 5, g, 1.2);
}
