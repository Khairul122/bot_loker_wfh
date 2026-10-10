// level 9: the meeting room: long table, chairs, whiteboard and a spot for discussions
import { box, group, tag, sign } from '../../core/factory.js';
import { chair, plant } from '../../world/props.js';
import { RAPAT } from '../divisions.js';
import { roomSpots } from '../floor.js';

export default function build(g) {
  // long meeting table
  const table = group(0, 0, 0.5, g);
  box(6.4, 0.12, 2.2, 0x8a6b55, 0, 0.78, 0, table);
  for (const sx of [-2.9, 2.9]) for (const sz of [-0.9, 0.9]) box(0.14, 0.78, 0.14, 0x5a3d2b, sx, 0.39, sz, table);
  tag(table, { kind: 'spot', kindName: 'rapat' });

  // chairs around the table, 4 per side
  for (let k = 0; k < 4; k++) {
    const x = -2.4 + k * 1.6;
    tag(chair(x, -0.95, 0, g, 0x5b9bd5), { kind: 'spot', kindName: 'rapat' });
    roomSpots.push({ kind: 'rapat', level: RAPAT, x, z: -0.95, ry: 0, pose: 'sit', emo: '💬', energy: 4 });
    tag(chair(x, 1.95, Math.PI, g, 0x5b9bd5), { kind: 'spot', kindName: 'rapat' });
    roomSpots.push({ kind: 'rapat', level: RAPAT, x, z: 1.95, ry: Math.PI, pose: 'sit', emo: '💬', energy: 4 });
  }
  // head seat for the owner
  tag(chair(-4.2, 0.5, Math.PI / 2, g, 0x8a6b55), { kind: 'spot', kindName: 'rapat' });
  roomSpots.push({ kind: 'rapat', level: RAPAT, x: -4.2, z: 0.5, ry: Math.PI / 2, pose: 'sit', emo: '👑', energy: 4 });

  // whiteboard on the back wall
  box(4.4, 2.2, 0.08, 0xffffff, 0, 2.1, -5.7, g);
  box(4.6, 0.1, 0.12, 0x8a6b55, 0, 0.95, -5.7, g, { cast: false });
  sign('💬', 'Ruang Rapat', '#5b9bd5', '#fff', 0, 3.6, -5.62, g, 3.2);
  // screen for slides
  box(2.8, 1.6, 0.08, 0x223344, 5.2, 2.2, -5.7, g, { glow: 0x8cc8ff, cast: false });

  plant(-8.2, 5.2, g, 1.2); plant(8.2, 5.2, g);
}
