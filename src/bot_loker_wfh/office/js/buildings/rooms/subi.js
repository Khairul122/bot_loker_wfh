// Subi's private office (Manajer Lamaran): manager desk facing the glass front, guest chairs, a parcel
// shelf and a launch-status board by the door, a reading sofa. The doorway (local x -1..1, z -5) stays clear.
import { box, cyl, group, tag, animated } from '../../core/factory.js';
import { pick } from '../../core/util.js';
import { chair, sofa, rug, plant } from '../../world/props.js';
import { DIVS } from '../divisions.js';
import { seats, solid, spot } from '../registry.js';

export default function build(g) {
  const lamar = DIVS.find(division => division.id === 'lamar');
  rug(0, 0.6, 2.2, 0x9fd3e2, g);
  seats('subi', [[0, 0.6]], g, lamar.screen);
  box(0.5, 0.3, 0.05, 0x3b3b48, 0.65, 1.02, 0.85, g); // second, smaller monitor
  box(0.45, 0.26, 0.02, lamar.screen, 0.65, 1.02, 0.82, g, { glow: lamar.screen, cast: false });
  for (const x of [-0.6, 0.6]) chair(x, 1.95, Math.PI, g, 0xd8b48a);

  // parcel shelf left of the door: one box per application waiting to go out
  box(1.8, 1.5, 0.45, 0xc89a6c, -1.95, 0.75, -4.55, g);
  box(1.6, 0.06, 0.4, lamar.accentColor, -1.95, 1.53, -4.55, g, { cast: false });
  for (let k = 0; k < 6; k++) box(0.42, 0.3, 0.32, k % 2 ? 0xd9b48a : 0xc4895a, -2.5 + (k % 3) * 0.55, 0.25 + Math.floor(k / 3) * 0.6, -4.45, g);
  solid(g, -1.95, -4.55, 1.8, 0.45);

  // launch board right of the door, on its own feet so it stays in the cutaway
  const board = group(1.95, 0, -4.5, g);
  for (const s of [-1, 1]) box(0.06, 2.1, 0.06, 0x9aa3ad, s * 0.8, 1.05, 0, board);
  box(1.7, 1.1, 0.06, 0xffffff, 0, 1.5, 0, board);
  const bars = Array.from({ length: 5 }, (_, k) => box(0.18, 1, 0.02, pick([0x4ea7c4, 0x6bb38a, 0xf2b84b]), -0.6 + k * 0.3, 1.5, 0.04, board, { cast: false }));
  animated.push(t => bars.forEach((b, k) => { const h = 0.35 + 0.45 * (0.5 + 0.5 * Math.sin(t * 0.6 + k)); b.scale.y = h; b.position.y = 1.0 + h / 2; }));
  solid(g, 1.95, -4.5, 1.7, 0.3);

  // reading sofa by the glass front
  tag(sofa(-2.3, 3.4, Math.PI / 2, g, 0x4ea7c4), { kind: 'spot', kindName: 'sofa' }); solid(g, -2.3, 3.4, 2.4, 0.9, Math.PI / 2);
  spot(g, { kind: 'sofa', x: -2.2, z: 3.4, ry: Math.PI / 2, pose: 'sit', emo: '🚀', energy: 6 });
  cyl(0.35, 0.35, 0.05, 0xc89a6c, -1, 0.5, 3.4, g); cyl(0.05, 0.05, 0.5, 0x8a6b55, -1, 0.25, 3.4, g); solid(g, -1, 3.4, 0.7, 0.7);
  plant(2.3, 4.3, g, 1.2); solid(g, 2.3, 4.3, 0.8, 0.8);
  plant(2.4, -2.6, g); solid(g, 2.4, -2.6, 0.7, 0.7);
}
