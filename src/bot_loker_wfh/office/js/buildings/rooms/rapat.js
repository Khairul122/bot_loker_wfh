// the meeting room: long table, eight chairs and the owner's head seat, whiteboard, slide screen
import { box, cyl, group, tag, sign } from '../../core/factory.js';
import { chair, plant } from '../../world/props.js';
import { solid, spot } from '../registry.js';

export default function build(g) {
  const table = group(-0.6, 0, -0.4, g);
  box(6.4, 0.12, 2.2, 0x8a6b55, 0, 0.78, 0, table);
  for (const sx of [-2.9, 2.9]) for (const sz of [-0.9, 0.9]) box(0.14, 0.78, 0.14, 0x5a3d2b, sx, 0.39, sz, table);
  for (let k = 0; k < 3; k++) cyl(0.12, 0.12, 0.05, 0x3b3b48, -2 + k * 2, 0.86, 0, table, { cast: false }); // conference mics
  tag(table, { kind: 'spot', kindName: 'rapat' }); solid(g, -0.6, -0.4, 6.4, 2.2);

  for (let k = 0; k < 4; k++) {
    const x = -3 + k * 1.6;
    tag(chair(x, -1.85, 0, g, 0x5b9bd5), { kind: 'spot', kindName: 'rapat' });
    spot(g, { kind: 'rapat', x, z: -1.85, ry: 0, pose: 'sit', emo: '💬', energy: 4 });
    tag(chair(x, 1.05, Math.PI, g, 0x5b9bd5), { kind: 'spot', kindName: 'rapat' });
    spot(g, { kind: 'rapat', x, z: 1.05, ry: Math.PI, pose: 'sit', emo: '💬', energy: 4 });
  }
  tag(chair(-4.6, -0.4, Math.PI / 2, g, 0x8a6b55), { kind: 'spot', kindName: 'rapat' });
  spot(g, { kind: 'rapat', x: -4.6, z: -0.4, ry: Math.PI / 2, pose: 'sit', emo: '👑', energy: 4 });

  // whiteboard and slide screen stand on their own feet, so they stay when the walls are cut away
  const wb = group(-1.2, 0, -3.3, g);
  for (const s of [-1, 1]) box(0.08, 2.3, 0.08, 0x9aa3ad, s * 1.85, 1.15, 0, wb);
  box(3.6, 1.6, 0.08, 0xffffff, 0, 1.45, 0, wb);
  sign('💬', 'Ruang Rapat', '#5b9bd5', '#fff', 0, 2.45, 0.05, wb, 2.6);
  solid(g, -1.2, -3.3, 3.8, 0.4);
  const tv = group(3.9, 0, -3.3, g);
  box(0.1, 1.4, 0.1, 0x3b3b48, 0, 0.7, 0, tv); box(2.4, 1.4, 0.08, 0x223344, 0, 1.6, 0, tv, { glow: 0x8cc8ff, cast: false });
  solid(g, 3.9, -3.3, 2.4, 0.4);
  box(0.5, 0.9, 2.2, 0x8a6b55, -5.45, 0.45, 1.8, g); solid(g, -5.45, 1.8, 0.5, 2.2);
  for (let k = 0; k < 4; k++) cyl(0.05, 0.05, 0.25, 0x9fd8ef, -5.45, 1.03, 1.1 + k * 0.45, g, { cast: false });
  plant(5.3, 3.3, g, 1.2); plant(-5.3, 3.4, g); solid(g, 5.3, 3.3, 0.8, 0.8); solid(g, -5.3, 3.4, 0.7, 0.7);
}
