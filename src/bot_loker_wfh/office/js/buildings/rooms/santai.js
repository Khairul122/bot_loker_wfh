// lounge: coffee bar, TV corner (the screen plays while someone watches), bean bags, foosball, arcade
import * as THREE from 'three';
import { box, cyl, sph, group, tag, animated } from '../../core/factory.js';
import { sofa, shelf, rug, plant } from '../../world/props.js';
import { solid, spot } from '../registry.js';

const used = s => s.by && s.by.spot === s;

export default function build(g) {
  // coffee bar along the back wall
  const bar = group(1.5, 0, -4.4, g);
  box(6, 1, 0.9, 0x6b4a33, 0, 0.5, 0, bar); box(6.2, 0.08, 1.05, 0xfff2df, 0, 1.04, 0, bar);
  for (const x of [-1.1, 1.1]) { box(0.5, 0.6, 0.45, 0x3b3b48, x, 1.38, -0.15, bar); cyl(0.07, 0.07, 0.12, 0xffffff, x, 1.14, 0.2, bar, { cast: false }); }
  for (let k = 0; k < 5; k++) cyl(0.06, 0.05, 0.1, 0xffffff, 2.2 + (k % 3) * 0.2, 1.13 + Math.floor(k / 3) * 0.1, 0.1, bar, { cast: false });
  tag(bar, { kind: 'spot', kindName: 'kopi' }); solid(g, 1.5, -4.4, 6, 0.9);
  for (const x of [0.4, 2.6]) spot(g, { kind: 'kopi', x, z: -3.1, ry: Math.PI, pose: 'stand', emo: '☕', energy: 10 });

  // TV corner
  box(0.6, 0.55, 2.8, 0x8a6b55, 5.95, 0.275, 1.4, g); solid(g, 5.95, 1.4, 0.6, 2.8);
  box(0.08, 1.5, 2.7, 0x2b2b35, 6.1, 1.5, 1.4, g);
  const tvMat = new THREE.MeshBasicMaterial({ color: 0x15151c });
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(2.5, 1.35), tvMat);
  screen.position.set(6.05, 1.5, 1.4); screen.rotation.y = -Math.PI / 2; g.add(screen);
  tag(sofa(2.6, 1.4, Math.PI / 2, g, 0xe9967a), { kind: 'spot', kindName: 'sofa' }); solid(g, 2.6, 1.4, 2.4, 0.9, Math.PI / 2);
  const watchers = [0.8, 2].map(z => spot(g, { kind: 'sofa', x: 2.7, z, ry: Math.PI / 2, pose: 'sit', emo: '📺', energy: 6, joy: 3 }));
  box(0.7, 0.4, 1.2, 0xc89a6c, 4.1, 0.2, 1.4, g); solid(g, 4.1, 1.4, 0.7, 1.2);
  rug(3.6, 1.4, 2.4, 0xf6c89f, g);
  for (const [x, z, c] of [[1.4, 3.9, 0xef8a6b], [3.2, 4, 0x6bb38a], [4.9, 3.6, 0x7aa6d8]]) {
    const bag = sph(0.55, c, x, 0.32, z, g); bag.scale.y = 0.6;
    tag(bag, { kind: 'spot', kindName: 'beanbag' }); solid(g, x, z, 1, 1);
    spot(g, { kind: 'beanbag', x, z, ry: 1.1, pose: 'floor', emo: '😌', energy: 7, joy: 2 });
  }

  // foosball: the rods spin while two people play
  const fb = group(-3, 0, 1.2, g);
  box(1.5, 0.3, 0.85, 0x2f6b4a, 0, 0.85, 0, fb); box(1.4, 0.02, 0.75, 0x4c9a6a, 0, 0.99, 0, fb, { cast: false });
  for (const [a, b] of [[-0.65, -0.35], [0.65, -0.35], [-0.65, 0.35], [0.65, 0.35]]) box(0.08, 0.7, 0.08, 0x3b3b48, a, 0.35, b, fb);
  const rods = [-0.5, -0.17, 0.17, 0.5].map((x, k) => {
    const rod = group(x, 1.05, 0, fb); cyl(0.02, 0.02, 1.2, 0xc0c7d6, 0, 0, 0, rod, { cast: false }).rotation.x = Math.PI / 2;
    for (const z of [-0.2, 0.2]) box(0.06, 0.18, 0.06, k < 2 ? 0xef6a5a : 0x5b9bd5, 0, -0.06, z, rod, { cast: false });
    return rod;
  });
  tag(fb, { kind: 'spot', kindName: 'foosball' }); solid(g, -3, 1.2, 1.5, 0.85);
  const players = [[-4.2, Math.PI / 2], [-1.8, -Math.PI / 2]].map(([x, ry]) => spot(g, { kind: 'foosball', x, z: 1.2, ry, pose: 'play', emo: '⚽', joy: 5, energy: -1 }));

  // arcade cabinet against the left wall
  const arc = group(-5.95, 0, -1.8, g);
  box(0.7, 1.8, 0.8, 0x5b3d8a, 0, 0.9, 0, arc); box(0.05, 0.5, 0.6, 0x9fe6ff, 0.36, 1.35, 0, arc, { glow: 0x9fe6ff, cast: false });
  box(0.3, 0.08, 0.6, 0x3b3b48, 0.45, 0.95, 0, arc);
  tag(arc, { kind: 'spot', kindName: 'arcade' }); solid(g, -5.95, -1.8, 0.7, 0.8);
  spot(g, { kind: 'arcade', x: -5.1, z: -1.8, ry: -Math.PI / 2, pose: 'play', emo: '🕹️', joy: 5 });
  shelf(-6, 3.4, Math.PI / 2, g); solid(g, -6, 3.4, 2, 0.5, Math.PI / 2);
  plant(5.9, 4.4, g, 1.2); plant(-5.9, -4.4, g, 1.2); solid(g, 5.9, 4.4, 0.8, 0.8); solid(g, -5.9, -4.4, 0.8, 0.8);

  animated.push((t, dt) => {
    if (watchers.some(used)) tvMat.color.setHSL((t * 0.07) % 1, 0.55, 0.42 + Math.sin(t * 9) * 0.07);
    else tvMat.color.setHex(0x15151c);
    if (players.some(used)) rods.forEach((r, k) => { r.rotation.z = Math.sin(t * 6 + k) * 0.9; });
  });
}
