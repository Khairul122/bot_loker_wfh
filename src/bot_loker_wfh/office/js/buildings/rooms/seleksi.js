// level 2: conveyor of job cards into a funnel (card count follows the queue)
import * as THREE from 'three';
import { add, mat, box, animated } from '../../core/factory.js';
import { pick } from '../../core/util.js';
import { shelf, plant } from '../../world/props.js';
import { seats, dyn } from '../floor.js';

export default function build(g, d) {
  seats('seleksi', [[-6, -3], [-2.2, -3]], g, d.screen);
  box(9, 0.5, 1.1, 0x6e6a8f, 3, 0.75, 1.5, g); box(9, 0.06, 0.9, 0x3b3b48, 3, 1.02, 1.5, g, { cast: false });
  const funnel = add(new THREE.ConeGeometry(1.1, 1.8, 18, 1, true), 0x8a86d8, 7, 2.3, 1.5, g); funnel.rotation.x = Math.PI;
  funnel.material = mat(0x8a86d8, { p: { side: THREE.DoubleSide } });
  const cards = [];
  for (let k = 0; k < 7; k++) { const c = box(0.6, 0.06, 0.45, pick([0xffffff, 0xffe9c6, 0xd6f5df]), 0, 1.09, 1.5, g, { cast: false }); c.userData.o = k / 7; cards.push(c); }
  dyn.cards = cards;
  animated.push(t => { for (const c of cards) { const u = (t * 0.08 + c.userData.o) % 1; c.position.x = -1.2 + u * 8.2; c.visible = c.userData.on !== false; } });
  shelf(-6, 3.5, Math.PI, g); plant(8, -5, g, 1.2);
}
