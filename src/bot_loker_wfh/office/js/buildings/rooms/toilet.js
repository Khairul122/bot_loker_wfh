// toilet: two stalls with doors that close while in use, a two-basin sink and a mirror
import { box, cyl, group, tag } from '../../core/factory.js';
import { plant } from '../../world/props.js';
import { solid, spot, wall, cutaway } from '../registry.js';

export const stalls = [];

export default function build(g) {
  const tile = 0xeaf3f6;
  const partition = group(0, 0, -2.8, g); box(0.12, 2.3, 2.4, tile, 0, 1.15, 0, partition); cutaway.cut.push(partition);
  wall(g, -0.06, 0.06, -4, -1.6);
  for (const s of [-1, 1]) {
    const x = s * 1.25;
    cyl(0.24, 0.2, 0.42, 0xffffff, x, 0.21, -3.35, g); box(0.5, 0.5, 0.18, 0xffffff, x, 0.6, -3.75, g);
    // the leaf hangs on the outer wall; it swings out while the stall is free
    const closed = s < 0 ? 0 : Math.PI, open = closed + (s < 0 ? -1.2 : 1.2);
    const hinge = group(s * 2.33, 0, -1.6, g); box(1.05, 2, 0.06, 0x7ab8d0, 0.52, 1.1, 0, hinge);
    hinge.rotation.y = open; cutaway.cut.push(hinge);
    const st = spot(g, { kind: 'toilet', x, z: -3.15, ry: 0, pose: 'sit', emo: '🚽', energy: 2 });
    stalls.push({ hinge, spot: st, open, closed });
    tag(hinge, { kind: 'spot', kindName: 'toilet' });
  }
  const sink = group(2.1, 0, 1, g);
  box(0.5, 0.85, 2.2, 0xffffff, 0, 0.42, 0, sink);
  for (const z of [-0.5, 0.5]) cyl(0.22, 0.16, 0.1, 0xdfeef3, -0.02, 0.88, z, sink, { cast: false });
  const mirror = box(0.04, 0.9, 1.9, 0xcfeaf5, 0.22, 1.75, 0, sink, { glow: 0xffffff, cast: false }); cutaway.upper.push(mirror);
  solid(g, 2.1, 1, 0.5, 2.2);
  spot(g, { kind: 'wastafel', x: 1.45, z: 1, ry: Math.PI / 2, pose: 'wash', obj: sink, emo: '🧼' });
  plant(-1.9, 3.3, g); solid(g, -1.9, 3.3, 0.7, 0.7);
}
