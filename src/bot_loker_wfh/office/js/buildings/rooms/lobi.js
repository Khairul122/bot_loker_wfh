// level 0: reception desk, sofas, coffee corner, floating paper plane
import * as THREE from 'three';
import { mat, box, sph, group, tag, animated } from '../../core/factory.js';
import { sofa, rug, plant } from '../../world/props.js';
import { deskSeats } from '../floor.js';

export default function build(g) {
  box(4.2, 1.1, 1, 0xf08a5d, -1, 0.55, -1.2, g); box(4.4, 0.1, 1.2, 0xfff2df, -1, 1.12, -1.2, g);
  deskSeats.lobi = [{ x: -1, z: -2.3, ry: 0, side: 2.6 }];
  tag(sofa(-6, 3, Math.PI / 2, g, 0x7aa6d8), { kind: 'spot', kindName: 'sofa' }); sofa(4, 3.8, Math.PI, g, 0xe9967a);
  rug(-1, 3, 2.4, 0xf6c89f, g); box(1.2, 0.4, 0.8, 0xc89a6c, -1, 0.2, 3, g);
  plant(-8, -5, g, 1.3); plant(7.8, -5, g, 1.3); plant(-8, 5, g);
  const plane = new THREE.Mesh(new THREE.ConeGeometry(0.6, 2, 3), mat(0x2aabee)); plane.rotation.z = -Math.PI / 2;
  const pg = group(4, 2.6, -3.5, g); pg.add(plane);
  animated.push(t => { pg.position.y = 2.6 + Math.sin(t * 1.5) * 0.15; pg.rotation.y = Math.sin(t * 0.7) * 0.4; });
  // coffee machine counter
  const cm = group(6.8, 0, -1.5, g);
  box(2.2, 1, 0.8, 0x8a6b55, 0, 0.5, 0, cm); box(0.5, 0.7, 0.5, 0x444455, -0.3, 1.35, 0, cm); sph(0.1, 0xffffff, 0.4, 1.07, 0, cm);
  tag(cm, { kind: 'spot', kindName: 'kopi' });
}
