// Pantau & Interview: a glass trophy cabinet (trophies = offers, medals = interviews) and a chart board
import { mat, box, cyl, group } from '../../core/factory.js';
import { pick } from '../../core/util.js';
import { DESK_ROWS } from '../../domain/office-plan.js';
import { seats, solid, dyn } from '../registry.js';

export default function build(g, d) {
  const { back, front } = DESK_ROWS;
  seats('pantau', [[-1.05, back], [1.05, back]], g, d.screen);
  const cab = group(-1.3, 0, front + 0.2, g);
  box(2.2, 0.5, 0.5, 0x8a6b55, 0, 0.25, 0, cab); box(2.2, 0.06, 0.5, 0x8a6b55, 0, 1.95, 0, cab);
  box(2.2, 1.4, 0.48, 0, 0, 1.2, 0, cab, { material: mat(0xcfeaf5, { p: { transparent: true, opacity: 0.25, depthWrite: false } }), cast: false });
  box(2.1, 0.04, 0.44, 0xffffff, 0, 1.22, 0, cab, { cast: false });
  solid(g, -1.3, front + 0.2, 2.2, 0.5);
  const trophies = [];
  for (let k = 0; k < 6; k++) { const tg = group(-0.85 + k * 0.34, 0.5, 0, cab); cyl(0.1, 0.05, 0.22, 0xf2c14e, 0, 0.15, 0, tg); cyl(0.07, 0.09, 0.07, 0x8a6b55, 0, 0.035, 0, tg); tg.visible = false; trophies.push(tg); }
  const medals = [];
  for (let k = 0; k < 6; k++) { const m = cyl(0.11, 0.11, 0.04, 0xc0c7d6, -0.85 + k * 0.34, 1.4, 0, cab); m.rotation.x = Math.PI / 2; m.visible = false; medals.push(m); }
  dyn.trophies = trophies; dyn.medals = medals;
  const wb = group(1.4, 0, front + 0.3, g);
  for (const s of [-1, 1]) box(0.06, 1.9, 0.06, 0x9aa3ad, s * 0.95, 0.95, 0, wb);
  box(2, 1.2, 0.06, 0xffffff, 0, 1.45, 0, wb);
  for (let k = 0; k < 5; k++) box(0.25, 0.2 + k * 0.17, 0.02, pick([0x6bb38a, 0xf2b84b, 0xd8738f]), -0.6 + k * 0.3, 0.95 + (0.2 + k * 0.17) / 2, 0.04, wb, { cast: false });
  solid(g, 1.4, front + 0.3, 2.1, 0.4);
}
