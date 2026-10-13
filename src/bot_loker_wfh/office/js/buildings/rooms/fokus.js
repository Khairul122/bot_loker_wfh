// the quiet room: a wall of books, two reading armchairs and a nap daybed
import { box, cyl, sph, group, tag } from '../../core/factory.js';
import { shelf, armchair, rug, plant } from '../../world/props.js';
import { solid, spot } from '../registry.js';

export default function build(g) {
  for (const x of [-3.2, -1.1, 1]) { shelf(x, -3.55, 0, g); solid(g, x, -3.55, 2, 0.5); }
  rug(-1.6, 1.2, 1.9, 0x9fbf8f, g);
  for (const [x, ry] of [[-2.8, Math.PI / 2], [-0.4, -Math.PI / 2]]) {
    tag(armchair(x, 1.2, ry, g), { kind: 'spot', kindName: 'baca' }); solid(g, x, 1.2, 1, 1);
    spot(g, { kind: 'baca', x: x + Math.sign(ry) * 0.05, z: 1.2, ry, pose: 'sit', emo: '📚', energy: 6, joy: 2 });
  }
  cyl(0.4, 0.4, 0.06, 0xc89a6c, -1.6, 0.6, 1.2, g); cyl(0.06, 0.06, 0.6, 0x8a6b55, -1.6, 0.3, 1.2, g); solid(g, -1.6, 1.2, 0.8, 0.8);
  // nap daybed, head toward the back wall
  const bed = group(3.3, 0, -1.8, g);
  box(1.3, 0.35, 2.1, 0x9a6b4a, 0, 0.18, 0, bed); box(1.2, 0.25, 2, 0xffffff, 0, 0.47, 0, bed);
  box(0.8, 0.14, 0.4, 0xfff6e0, 0, 0.66, -0.75, bed); box(1.22, 0.08, 1.2, 0x7aa6d8, 0, 0.63, 0.35, bed);
  tag(bed, { kind: 'spot', kindName: 'nap' }); solid(g, 3.3, -1.8, 1.3, 2.1);
  spot(g, { kind: 'nap', x: 3.3, z: -0.8, ry: 0, pose: 'lie', emo: '😴', energy: 12 });
  const lampG = group(-3.9, 0, 2.9, g); cyl(0.04, 0.05, 1.6, 0x5a4a42, 0, 0.8, 0, lampG); sph(0.22, 0xfff1c9, 0, 1.7, 0, lampG, { glow: 0xffd27a });
  plant(3.9, 3.3, g, 1.2); solid(g, 3.9, 3.3, 0.8, 0.8);
}
