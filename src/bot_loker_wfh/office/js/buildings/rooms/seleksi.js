// Seleksi: a conveyor of job cards into a funnel (card count follows the queue)
import * as THREE from 'three';
import { add, mat, box, animated } from '../../core/factory.js';
import { pick } from '../../core/util.js';
import { DESK_ROWS } from '../../domain/office-plan.js';
import { seats, solid, dyn } from '../registry.js';

export default function build(g, d) {
  const { back, front } = DESK_ROWS;
  seats('seleksi', [[-1.05, back], [1.05, back]], g, d.screen);
  box(4.2, 0.5, 0.9, 0x6e6a8f, -0.4, 0.75, front, g); box(4.2, 0.06, 0.7, 0x3b3b48, -0.4, 1.02, front, g, { cast: false });
  for (const x of [-2.3, 1.5]) for (const s of [-1, 1]) box(0.08, 0.5, 0.08, 0x55606e, x, 0.25, front + s * 0.35, g);
  solid(g, -0.2, front, 4.8, 1);
  const funnel = add(new THREE.ConeGeometry(0.8, 1.4, 18, 1, true), 0x8a86d8, 1.9, 1.9, front, g); funnel.rotation.x = Math.PI;
  funnel.material = mat(0x8a86d8, { p: { side: THREE.DoubleSide } });
  const cards = [];
  for (let k = 0; k < 7; k++) { const c = box(0.5, 0.05, 0.4, pick([0xffffff, 0xffe9c6, 0xd6f5df]), 0, 1.08, front, g, { cast: false }); c.userData.o = k / 7; cards.push(c); }
  dyn.cards = cards;
  animated.push(t => { for (const c of cards) { const u = (t * 0.08 + c.userData.o) % 1; c.position.x = -2.3 + u * 4.1; c.visible = c.userData.on !== false; } });
}
