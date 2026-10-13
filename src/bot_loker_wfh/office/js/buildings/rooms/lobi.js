// lobby: reception desk (Lobi & Operasional), logo wall with a live clock, waiting sofa
import * as THREE from 'three';
import { mat, box, cyl, group, sign, tag, animated } from '../../core/factory.js';
import { sofa, rug, plant, chair, screens } from '../../world/props.js';
import { DIVS } from '../divisions.js';
import { deskSeats, solid, spot, toWorld } from '../registry.js';

export default function build(g) {
  const lobi = DIVS.find(d => d.id === 'lobi');
  const rc = group(-3, 0, -0.3, g);
  box(3.2, 1.05, 1, 0xfff2df, 0, 0.525, 0, rc); box(3.4, 0.08, 1.15, 0x8a6b55, 0, 1.09, 0, rc);
  box(3.2, 0.5, 0.04, lobi.accentColor, 0, 0.55, 0.52, rc, { cast: false });
  box(0.8, 0.5, 0.05, 0x3b3b48, 0.6, 1.4, -0.2, rc);
  screens.push(box(0.72, 0.42, 0.02, lobi.screen, 0.6, 1.4, -0.23, rc, { glow: lobi.screen, unique: true, cast: false }));
  solid(g, -3, -0.3, 3.2, 1);
  chair(-3, -1.1, 0, g, 0x7a8fb8);
  deskSeats.lobi = [{ ...toWorld(g, -3, -1.1), ry: 0 }];

  // logo wall: freestanding, so it stays up in the cutaway; the clock shows the real time
  const wallG = group(-3, 0, -2.6, g);
  box(3.8, 2.6, 0.2, 0x3f4a5a, 0, 1.3, 0, wallG);
  sign('🏢', 'Loker WFH', lobi.accent, '#ffffff', 0, 1.45, 0.11, wallG, 3.4);
  const face = cyl(0.32, 0.32, 0.04, 0xffffff, 0, 2.2, 0.12, wallG, { cast: false }); face.rotation.x = Math.PI / 2;
  const hand = (len, w) => { const p = group(0, 2.2, 0.15, wallG); box(w, len, 0.02, 0x3f4a5a, 0, len / 2, 0, p, { cast: false }); return p; };
  const hourHand = hand(0.17, 0.05), minHand = hand(0.26, 0.03);
  animated.push(() => {
    const now = new Date(), m = now.getMinutes() + now.getSeconds() / 60;
    minHand.rotation.z = -m / 60 * Math.PI * 2; hourHand.rotation.z = -((now.getHours() % 12) + m / 60) / 12 * Math.PI * 2;
  });
  solid(g, -3, -2.6, 3.8, 0.2);

  tag(sofa(4.6, 0.8, -Math.PI / 2, g, 0x7aa6d8), { kind: 'spot', kindName: 'sofa' }); solid(g, 4.6, 0.8, 2.4, 0.9, -Math.PI / 2);
  for (const z of [0.2, 1.4]) spot(g, { kind: 'sofa', x: 4.5, z, ry: -Math.PI / 2, pose: 'sit', emo: '🛋️', energy: 6 });
  box(0.7, 0.4, 1.2, 0xc89a6c, 3.3, 0.2, 0.8, g); solid(g, 3.3, 0.8, 0.7, 1.2);
  box(0.4, 0.03, 0.3, 0xef8a6b, 3.3, 0.42, 0.6, g, { cast: false });
  rug(0, 1.8, 2, 0xf6c89f, g);
  for (const [x, z] of [[5.3, 4.3], [-5.3, 4.3], [5.3, -4.3], [-5.4, -4.3]]) { plant(x, z, g, 1.3); solid(g, x, z, 0.8, 0.8); }
  // a paper plane drifts over the lobby
  const plane = new THREE.Mesh(new THREE.ConeGeometry(0.5, 1.6, 3), mat(0x2aabee)); plane.rotation.z = -Math.PI / 2;
  const pg = group(2.4, 2.6, -2.2, g); pg.add(plane);
  animated.push(t => { pg.position.y = 2.6 + Math.sin(t * 1.5) * 0.15; pg.rotation.y = Math.sin(t * 0.7) * 0.4; });
}
