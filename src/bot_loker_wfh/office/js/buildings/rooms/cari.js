// level 1: job hunters' desks, spinning globe, telescope
import { cyl, sph, group, animated } from '../../core/factory.js';
import { plant } from '../../world/props.js';
import { seats } from '../floor.js';

export default function build(g, d) {
  seats('cari', [[-6, -3], [-2.2, -3], [1.6, -3], [-6, 1.2], [-2.2, 1.2], [1.6, 1.2]], g, d.screen);
  const globe = group(6.2, 0, 2.5, g); cyl(0.1, 0.4, 1.2, 0xc89a6c, 0, 0.6, 0, globe);
  sph(0.7, 0x7cc6e8, 0, 1.8, 0, globe); sph(0.705, 0x8fcf7a, 0.2, 1.9, 0.1, globe, { cast: false }).scale.set(0.6, 0.5, 0.6);
  animated.push(t => { globe.rotation.y = t * 0.4; });
  const tel = group(6.5, 0, -3.5, g, -0.6); cyl(0.05, 0.05, 1.3, 0x5a4a42, 0, 0.65, 0, tel);
  const tube = cyl(0.15, 0.2, 1.4, 0xf2b84b, 0, 1.5, 0.2, tel); tube.rotation.x = -0.9;
  plant(8, 5, g); plant(-8, 5, g, 1.2);
}
