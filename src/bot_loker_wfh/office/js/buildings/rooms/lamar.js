// level 4: mailbox and circling paper planes (one per sent application)
import * as THREE from 'three';
import { mat, box, cyl, group, animated } from '../../core/factory.js';
import { plant } from '../../world/props.js';
import { seats, dyn } from '../floor.js';

export default function build(g, d) {
  seats('lamar', [[-5, -3], [-1.2, -3]], g, d.screen);
  const mb = group(5, 0, 2, g); cyl(0.08, 0.08, 1, 0x5a4a42, 0, 0.5, 0, mb); box(0.8, 0.6, 1.1, 0x4ea7c4, 0, 1.25, 0, mb); box(0.08, 0.5, 0.06, 0xef6a5a, 0.42, 1.6, 0.2, mb);
  const planes = [];
  for (let k = 0; k < 8; k++) { const pl = new THREE.Mesh(new THREE.ConeGeometry(0.25, 0.8, 3), mat(0xffffff)); pl.rotation.z = -Math.PI / 2; const pgp = group(0, 0, 0, g); pgp.add(pl); pgp.userData.o = k * 0.8; planes.push(pgp); }
  dyn.planes = planes;
  animated.push(t => planes.forEach(p => { const a = t * 0.6 + p.userData.o; p.position.set(Math.cos(a) * 4 + 2, 2.6 + Math.sin(a * 2) * 0.3, Math.sin(a) * 2.5 + 1.5); p.rotation.y = -a; }));
  plant(-8, 5, g, 1.2); plant(8, -5, g);
}
