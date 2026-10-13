// Lamaran: a mailbox, a shelf of parcels and circling paper planes (one per sent application)
import * as THREE from 'three';
import { mat, box, cyl, group, animated } from '../../core/factory.js';
import { DESK_ROWS } from '../../domain/office-plan.js';
import { seats, solid, dyn } from '../registry.js';

export default function build(g, d) {
  const { back, front } = DESK_ROWS;
  seats('lamar', [[0, back]], g, d.screen); // Faris; the manager, Subi, works in Ruang Subi
  const mb = group(-1.3, 0, front, g); cyl(0.08, 0.08, 1, 0x5a4a42, 0, 0.5, 0, mb); box(0.8, 0.6, 1.1, 0x4ea7c4, 0, 1.25, 0, mb); box(0.08, 0.5, 0.06, 0xef6a5a, 0.42, 1.6, 0.2, mb);
  solid(g, -1.3, front, 0.9, 1.1);
  box(1.8, 1.4, 0.45, 0xc89a6c, 1.3, 0.7, front + 0.3, g); solid(g, 1.3, front + 0.3, 1.8, 0.45);
  for (let k = 0; k < 6; k++) box(0.4, 0.3, 0.35, k % 2 ? 0xd9b48a : 0xc4895a, 0.75 + (k % 3) * 0.55, 1.55 + Math.floor(k / 3) * 0.32, front + 0.3, g);
  const planes = [];
  for (let k = 0; k < 8; k++) { const pl = new THREE.Mesh(new THREE.ConeGeometry(0.2, 0.65, 3), mat(0xffffff)); pl.rotation.z = -Math.PI / 2; const pg = group(0, 0, 0, g); pg.add(pl); pg.userData.o = k * 0.8; planes.push(pg); }
  dyn.planes = planes;
  animated.push(t => planes.forEach(p => { const a = t * 0.6 + p.userData.o; p.position.set(Math.cos(a) * 2, 2.5 + Math.sin(a * 2) * 0.25, front - 1 + Math.sin(a) * 1.2); p.rotation.y = -a; }));
}
