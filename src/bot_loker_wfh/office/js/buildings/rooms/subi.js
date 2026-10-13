// Subi's private workspace for reviewing and sending applications.
import { box } from '../../core/factory.js';
import { plant } from '../../world/props.js';
import { DIVS } from '../divisions.js';
import { seats, solid } from '../registry.js';

export default function build(g) {
  const lamar = DIVS.find(division => division.id === 'lamar');
  seats('subi', [[0, -1.35]], g, lamar.screen);

  box(1.8, 1.4, 0.45, 0xc89a6c, -2.1, 0.7, -3.2, g);
  box(1.5, 0.06, 0.4, lamar.accentColor, -2.1, 1.43, -3.2, g, { cast: false });
  for (let k = 0; k < 4; k++) box(0.42, 0.32, 0.34, k % 2 ? 0xd9b48a : 0xc4895a, -2.55 + (k % 2) * 0.9, 1.62 + Math.floor(k / 2) * 0.34, -3.2, g);
  solid(g, -2.1, -3.2, 1.8, 0.45);

  plant(2.1, 3.1, g, 0.9);

  box(2.8, 1.35, 0.08, 0x3f4a5a, 0, 1.65, -4.7, g);
  box(2.55, 1.12, 0.03, lamar.screen, 0, 1.65, -4.64, g, { glow: lamar.screen, cast: false });
  solid(g, 0, -4.7, 2.8, 0.08);
}
