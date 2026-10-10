// the chibi body every character shares, and the moods its face can show
import * as THREE from 'three';
import { add, box, sph } from '../core/factory.js';

export const MOODS = {
  semangat: { emo: '🤩', label: 'Semangat banget', face: 'open', cheeks: true },
  senang: { emo: '😊', label: 'Senang', face: 'smile', cheeks: true },
  fokus: { emo: '🧐', label: 'Fokus', face: 'flat' },
  lelah: { emo: '😮‍💨', label: 'Lelah', face: 'frown' },
  sedih: { emo: '😢', label: 'Sedih', face: 'frown' },
  ngantuk: { emo: '😴', label: 'Ngantuk', face: 'sleep' },
};
export const LADDER = ['ngantuk', 'lelah', 'fokus', 'senang', 'semangat'];

function capsule(r, len, color, parent, x, y, z) {
  return add(new THREE.CapsuleGeometry(r, len, 4, 10), color, x, y, z, parent, { unique: true });
}
export function makeBody(look) {
  const root = new THREE.Group();
  const body = new THREE.Group(); root.add(body);
  const hip = new THREE.Group(); hip.position.y = 0.62; body.add(hip);
  const legs = [-0.12, 0.12].map(x => { const p = new THREE.Group(); p.position.x = x; hip.add(p); capsule(0.09, 0.36, look.pants, p, 0, -0.3, 0); sph(0.1, 0x4a3a32, 0, -0.56, 0.04, p); return p; });
  const torso = capsule(0.25, 0.32, look.shirt, body, 0, 0.98, 0);
  const head = new THREE.Group(); head.position.y = 1.52; body.add(head);
  const skull = sph(0.31, look.skin, 0, 0, 0, head, { unique: true });
  const hair = add(new THREE.SphereGeometry(0.33, 18, 12, 0, Math.PI * 2, 0, Math.PI * 0.5), look.hair, 0, 0.03, -0.02, head, { unique: true });
  hair.rotation.x = -0.25;
  if (look.bun) sph(0.13, look.hair, 0, 0.3, -0.2, head, { material: hair.material });
  const eyes = [-0.1, 0.1].map(x => sph(0.045, 0x2b211c, x, 0.02, 0.28, head, { cast: false }));
  const cheeks = [-0.17, 0.17].map(x => { const c = sph(0.05, 0xff9fa0, x, -0.07, 0.25, head, { cast: false }); c.scale.z = 0.4; return c; });
  const smile = add(new THREE.TorusGeometry(0.07, 0.016, 6, 12, Math.PI), 0x6b3a2e, 0, -0.08, 0.29, head, { cast: false }); smile.rotation.z = Math.PI;
  const frown = add(new THREE.TorusGeometry(0.06, 0.016, 6, 12, Math.PI), 0x6b3a2e, 0, -0.13, 0.29, head, { cast: false });
  const flat = box(0.1, 0.02, 0.02, 0x6b3a2e, 0, -0.1, 0.29, head, { cast: false });
  const open = sph(0.05, 0x6b3a2e, 0, -0.1, 0.28, head, { cast: false }); open.scale.set(1, 1.2, 0.5);
  const arms = [-1, 1].map(s => { const p = new THREE.Group(); p.position.set(s * 0.33, 1.2, 0); body.add(p); capsule(0.075, 0.32, look.shirt, p, 0, -0.22, 0); sph(0.08, look.skin, 0, -0.45, 0, p, { unique: true }); return p; });
  const parts = { root, body, hip, legs, torso, head, skull, hair, eyes, cheeks, mouth: { smile, frown, flat, open }, arms };
  root.traverse(o => { if (o.isMesh) o.castShadow = true; });
  return parts;
}
