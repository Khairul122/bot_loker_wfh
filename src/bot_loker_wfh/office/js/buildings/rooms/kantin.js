// level 7: canteen (buffet counter, three tables) + toilet room with two stalls and a sink
import * as THREE from 'three';
import { scene } from '../../core/engine.js';
import { gradient, box, cyl, sph, group, sign, tag, emojiTex } from '../../core/factory.js';
import { FH, V } from '../../core/util.js';
import { chair, plant } from '../../world/props.js';
import { ROOM_WALLS } from '../../world/navigation.js';
import { KANTIN } from '../divisions.js';
import { roomSpots } from '../floor.js';

export const FOODS = [
  { id: 'nasgor', icon: '🍛', name: 'Nasi Goreng', energy: 35, joy: 6 },
  { id: 'mie', icon: '🍜', name: 'Mie Ayam', energy: 30, joy: 8 },
  { id: 'bakso', icon: '🍲', name: 'Bakso', energy: 28, joy: 10 },
  { id: 'esteh', icon: '🧋', name: 'Es Teh', energy: 12, joy: 12 },
];
export const ORDER_AT = [V(-6, -3.4), V(-4.4, -3.4), V(-2.8, -3.4)]; // in front of the counter
export const stalls = [];

export default function build(g) {
  // buffet counter along the back wall
  const ct = group(-4.4, 0, -4.7, g);
  box(6.4, 1, 0.9, 0xc4895a, 0, 0.5, 0, ct); box(6.6, 0.08, 1.05, 0xfff2df, 0, 1.04, 0, ct);
  [0xf2b84b, 0xd8643a, 0x8fcf7a, 0xf6e7c1, 0xb5651d, 0xffd166].forEach((c, k) => {
    box(0.8, 0.1, 0.55, 0xd9dde3, -2.6 + k * 1.04, 1.12, 0, ct, { cast: false });
    sph(0.26, c, -2.6 + k * 1.04, 1.17, 0, ct, { cast: false }).scale.y = 0.35;
  });
  box(6.4, 0.5, 0.04, 0, 0, 1.5, 0.38, ct, { cast: false, material: new THREE.MeshToonMaterial({ color: 0xcfeaf5, gradientMap: gradient, transparent: true, opacity: 0.35 }) });
  tag(ct, { kind: 'spot', kindName: 'kantin' });
  // three tables, four seats each; a plate sprite appears while someone eats
  [-6.6, -2.6, 1.4].forEach((tx, ti) => {
    const tz = 2.4;
    box(1.8, 0.08, 1, 0xe6c49a, tx, 0.74, tz, g); cyl(0.08, 0.2, 0.72, 0xb98d63, tx, 0.36, tz, g);
    for (const sx of [-0.45, 0.45]) for (const sz of [-1, 1]) {
      const x = tx + sx, z = tz + sz * 0.9;
      tag(chair(x, z, sz > 0 ? Math.PI : 0, g, 0xe0844a), { kind: 'spot', kindName: 'kantin' });
      const plate = new THREE.Sprite(new THREE.SpriteMaterial({ map: emojiTex('🍛', false), depthWrite: false }));
      plate.scale.setScalar(0.42); plate.position.set(x, KANTIN * FH + 0.95, tz + sz * 0.3); plate.visible = false; scene.add(plate);
      roomSpots.push({ kind: 'makan', level: KANTIN, x, z, ry: sz > 0 ? Math.PI : 0, pose: 'eat', table: ti, plate, emo: '😋' });
    }
  });
  // toilet room in the back-right corner: two stalls + a sink, its door on the left of the front wall
  const tile = 0xeaf3f6;
  box(0.15, FH - 0.4, 4.4, tile, 4, (FH - 0.4) / 2, -3.75, g);
  box(0.6, FH - 0.4, 0.15, tile, 4.3, (FH - 0.4) / 2, -1.55, g);
  box(3.2, FH - 0.4, 0.15, tile, 7.2, (FH - 0.4) / 2, -1.55, g);
  box(1, FH - 3, 0.15, tile, 5.1, 2.6 + (FH - 3) / 2, -1.55, g);
  ROOM_WALLS.push([3.9, 4.1, -6, -1.5, KANTIN], [4, 4.6, -1.65, -1.45, KANTIN], [5.6, 8.8, -1.65, -1.45, KANTIN]);
  sign('🚻', 'Toilet', '#4ea7c4', '#fff', 7.2, 3, -1.46, g, 2.6);
  box(4.8, 0.02, 4.3, 0xdfeef3, 6.4, 0.012, -3.75, g, { cast: false });
  const toiletBox = [4, 8.8, -6, -1.5];
  [6.7, 8.1].forEach(x => {
    box(0.1, 2.2, 1.7, 0xb9d7e2, x - 0.7, 1.1, -5.05, g);
    cyl(0.24, 0.2, 0.42, 0xffffff, x, 0.21, -5.35, g); box(0.5, 0.5, 0.18, 0xffffff, x, 0.6, -5.75, g);
    const hinge = group(x - 0.65, 0, -4.2, g); box(1.25, 2, 0.06, 0x7ab8d0, 0.62, 1.1, 0, hinge); hinge.rotation.y = -1.2;
    const spot = { kind: 'toilet', level: KANTIN, x, z: -5.1, ry: 0, pose: 'sit', emo: '🚽', energy: 2,
      via: [V(5.1, -0.4), V(5.1, -2.4), V(x, -3.4)], box: toiletBox };
    stalls.push({ hinge, spot }); roomSpots.push(spot);
    tag(hinge, { kind: 'spot', kindName: 'toilet' });
  });
  box(0.1, 2.2, 1.7, 0xb9d7e2, 8.8, 1.1, -5.05, g);
  const sink = group(4.35, 0, -3.2, g);
  box(0.5, 0.85, 0.9, 0xffffff, 0, 0.42, 0, sink); cyl(0.25, 0.18, 0.12, 0xdfeef3, 0.05, 0.9, 0, sink);
  box(0.04, 0.9, 0.8, 0xcfeaf5, -0.24, 1.75, 0, sink, { glow: 0xffffff, cast: false });
  roomSpots.push({ kind: 'wastafel', level: KANTIN, x: 5, z: -3.2, ry: -Math.PI / 2, pose: 'wash', obj: sink, emo: '🧼',
    via: [V(5.1, -0.4), V(5.1, -2.4)], box: toiletBox });
  plant(-8.2, 5.2, g, 1.2); plant(8.2, 5.2, g);
  const wd = group(-8.3, 0, -1.2, g); box(0.5, 1, 0.5, 0xffffff, 0, 0.5, 0, wd); cyl(0.2, 0.2, 0.5, 0x9fd8ef, 0, 1.25, 0, wd); // water dispenser
}
