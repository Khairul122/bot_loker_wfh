// ---------- emoji particle bursts ----------
import * as THREE from 'three';
import { scene } from '../core/engine.js';
import { emojiTex } from '../core/factory.js';
import { rand, pick, clamp } from '../core/util.js';

const parts = [];
export function burst(pos, emojis, n = 6) {
  for (let i = 0; i < n; i++) {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: emojiTex(pick(emojis), false), transparent: true, depthWrite: false }));
    s.position.copy(pos).add(new THREE.Vector3(rand(-0.5, 0.5), 2 + rand(0, 0.5), rand(-0.5, 0.5)));
    s.scale.setScalar(0.45); s.userData = { v: new THREE.Vector3(rand(-0.6, 0.6), rand(1.2, 2.2), rand(-0.6, 0.6)), life: 1.6 };
    scene.add(s); parts.push(s);
  }
}
export function updateParts(dt) {
  for (let i = parts.length - 1; i >= 0; i--) {
    const s = parts[i], u = s.userData; u.life -= dt;
    s.position.addScaledVector(u.v, dt); u.v.y -= dt * 0.8;
    s.material.opacity = clamp(u.life, 0, 1);
    if (u.life <= 0) { scene.remove(s); s.material.dispose(); parts.splice(i, 1); }
  }
}
// a character's feet, for bursts and effects
export const at = c => new THREE.Vector3(c.pos.x, c.y, c.pos.z);
