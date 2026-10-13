// canteen: buffet counter, four tables of four, a drinks fridge and a water dispenser
import * as THREE from 'three';
import { gradient, box, cyl, sph, group, sign, tag, emojiTex } from '../../core/factory.js';
import { V } from '../../core/util.js';
import { chair, plant } from '../../world/props.js';
import { solid, spot, toWorld, cutaway } from '../registry.js';

export const FOODS = [
  { id: 'nasgor', icon: '🍛', name: 'Nasi Goreng', energy: 35, joy: 6 },
  { id: 'mie', icon: '🍜', name: 'Mie Ayam', energy: 30, joy: 8 },
  { id: 'bakso', icon: '🍲', name: 'Bakso', energy: 28, joy: 10 },
  { id: 'esteh', icon: '🧋', name: 'Es Teh', energy: 12, joy: 12 },
];
export const ORDER_AT = []; // queue spots in front of the counter, world space

export default function build(g) {
  const ct = group(-2.3, 0, -4.4, g);
  box(7.6, 1, 0.9, 0xc4895a, 0, 0.5, 0, ct); box(7.8, 0.08, 1.05, 0xfff2df, 0, 1.04, 0, ct);
  [0xf2b84b, 0xd8643a, 0x8fcf7a, 0xf6e7c1, 0xb5651d, 0xffd166, 0xe9967a].forEach((c, k) => {
    box(0.8, 0.1, 0.55, 0xd9dde3, -3.1 + k * 1.03, 1.12, 0, ct, { cast: false });
    sph(0.26, c, -3.1 + k * 1.03, 1.17, 0, ct, { cast: false }).scale.y = 0.35;
  });
  box(7.6, 0.5, 0.04, 0, 0, 1.5, 0.38, ct, { cast: false, material: new THREE.MeshToonMaterial({ color: 0xcfeaf5, gradientMap: gradient, transparent: true, opacity: 0.35 }) });
  tag(ct, { kind: 'spot', kindName: 'kantin' }); solid(g, -2.3, -4.4, 7.6, 0.9);
  cutaway.upper.push(sign('🍜', 'Menu Hari Ini', '#d98b5f', '#fff', -2.3, 2.5, -4.82, g, 3.4));
  for (const x of [-4.6, -3.2, -1.8]) { const p = toWorld(g, x, -3.1); ORDER_AT.push(V(p.x, p.z)); }

  // four tables, four seats each; a plate sprite appears while someone eats
  [[-3.8, 0.2], [1.2, 0.2], [-3.8, 3.1], [1.2, 3.1]].forEach(([tx, tz], ti) => {
    box(1.8, 0.08, 1, 0xe6c49a, tx, 0.74, tz, g); cyl(0.08, 0.2, 0.72, 0xb98d63, tx, 0.36, tz, g);
    solid(g, tx, tz, 1.8, 1);
    for (const sx of [-0.45, 0.45]) for (const sz of [-1, 1]) {
      const x = tx + sx, z = tz + sz * 0.9;
      tag(chair(x, z, sz > 0 ? Math.PI : 0, g, 0xe0844a), { kind: 'spot', kindName: 'kantin' });
      const plate = new THREE.Sprite(new THREE.SpriteMaterial({ map: emojiTex('🍛', false), depthWrite: false }));
      plate.scale.setScalar(0.42); plate.position.set(x, 0.95, tz + sz * 0.3); plate.visible = false; g.add(plate);
      spot(g, { kind: 'makan', x, z, ry: sz > 0 ? Math.PI : 0, pose: 'eat', table: ti, plate, emo: '😋' });
    }
  });
  const fridge = group(5.95, 0, 1.2, g);
  box(0.7, 1.9, 1.1, 0xf4f7fa, 0, 0.95, 0, fridge); box(0.04, 1.6, 0.9, 0xbfe3f2, -0.36, 1.05, 0, fridge, { glow: 0xdff4ff, cast: false });
  for (let k = 0; k < 6; k++) cyl(0.06, 0.06, 0.22, [0xef6a5a, 0xf2b84b, 0x6bb38a][k % 3], -0.25, 0.6 + Math.floor(k / 3) * 0.5, -0.3 + (k % 3) * 0.3, fridge, { cast: false });
  solid(g, 5.95, 1.2, 0.7, 1.1);
  const wd = group(5.95, 0, -2.6, g); box(0.5, 1, 0.5, 0xffffff, 0, 0.5, 0, wd); cyl(0.2, 0.2, 0.5, 0x9fd8ef, 0, 1.25, 0, wd);
  tag(wd, { kind: 'spot', kindName: 'minum' }); solid(g, 5.95, -2.6, 0.5, 0.5);
  spot(g, { kind: 'minum', x: 5.25, z: -2.6, ry: Math.PI / 2, pose: 'stand', emo: '💧', energy: 6 });
  plant(-5.9, 4.4, g, 1.2); plant(5.9, 4.4, g, 1.2); solid(g, -5.9, 4.4, 0.8, 0.8); solid(g, 5.9, 4.4, 0.8, 0.8);
}
