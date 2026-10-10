// level 5: meeting room, whiteboard chart, trophy shelf (trophies = offers, medals = interviews)
import { box, cyl, group } from '../../core/factory.js';
import { pick } from '../../core/util.js';
import { chair, plant } from '../../world/props.js';
import { seats, dyn } from '../floor.js';

export default function build(g, d) {
  seats('pantau', [[-5.5, -3], [-1.7, -3]], g, d.screen);
  cyl(1.6, 1.6, 0.1, 0xe6c49a, 3, 0.78, 1.5, g); cyl(0.12, 0.3, 0.75, 0xb98d63, 3, 0.38, 1.5, g);
  for (let k = 0; k < 4; k++) { const a = k * Math.PI / 2 + 0.6; chair(3 + Math.cos(a) * 2.3, 1.5 + Math.sin(a) * 2.3, -a - Math.PI / 2, g, 0xd8738f); }
  box(3.5, 2, 0.1, 0xffffff, 3, 2, -5.7, g); // whiteboard
  for (let k = 0; k < 5; k++) box(0.4, 0.3 + k * 0.25, 0.04, pick([0x6bb38a, 0xf2b84b, 0xd8738f]), 1.8 + k * 0.6, 1.3 + (0.3 + k * 0.25) / 2, -5.63, g, { cast: false });
  box(3, 0.1, 0.6, 0xc89a6c, -6, 1.6, 4.5, g); box(3, 0.1, 0.6, 0xc89a6c, -6, 2.4, 4.5, g); // trophy shelf
  const trophies = [];
  for (let k = 0; k < 6; k++) { const tg = group(-7.1 + k * 0.45, 1.65, 4.5, g); cyl(0.12, 0.06, 0.25, 0xf2c14e, 0, 0.17, 0, tg); cyl(0.08, 0.1, 0.08, 0x8a6b55, 0, 0.04, 0, tg); tg.visible = false; trophies.push(tg); }
  const medals = [];
  for (let k = 0; k < 6; k++) { const m = cyl(0.13, 0.13, 0.04, 0xc0c7d6, -7.1 + k * 0.45, 2.62, 4.4, g); m.rotation.x = Math.PI / 2; m.visible = false; medals.push(m); }
  dyn.trophies = trophies; dyn.medals = medals;
  plant(8, 5, g, 1.2);
}
