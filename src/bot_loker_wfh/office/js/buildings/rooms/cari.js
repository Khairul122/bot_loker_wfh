// Pencarian Kerja: six desks; a spinning globe and a telescope at the quiet end of the back corridor
import { cyl, sph, group, animated } from '../../core/factory.js';
import { DESK_ROWS } from '../../domain/office-plan.js';
import { seats, solid } from '../registry.js';

export default function build(g, d) {
  const { back, front } = DESK_ROWS;
  seats('cari', [back, front].flatMap(z => [-2.1, 0, 2.1].map(x => [x, z])), g, d.screen);
  const globe = group(-2.4, 0, -5.5, g); cyl(0.1, 0.4, 1.2, 0xc89a6c, 0, 0.6, 0, globe);
  sph(0.7, 0x7cc6e8, 0, 1.8, 0, globe); sph(0.705, 0x8fcf7a, 0.2, 1.9, 0.1, globe, { cast: false }).scale.set(0.6, 0.5, 0.6);
  animated.push(t => { globe.rotation.y = t * 0.4; });
  solid(g, -2.4, -5.5, 1.2, 1.2);
  const tel = group(-0.6, 0, -5.6, g, -0.6); cyl(0.05, 0.05, 1.3, 0x5a4a42, 0, 0.65, 0, tel);
  const tube = cyl(0.15, 0.2, 1.4, 0xf2b84b, 0, 1.5, 0.2, tel); tube.rotation.x = -0.9;
  solid(g, -0.6, -5.6, 0.7, 0.7);
}
