// ---------- speech bubbles: HTML labels that follow a character on screen ----------
import * as THREE from 'three';
import { camera } from '../core/engine.js';
import { $ } from '../ui/dom.js';

const bubbles = new Map();
export function say(c, text, dur = 3.6) {
  let b = bubbles.get(c);
  if (!b) { b = document.createElement('div'); b.className = 'bub'; $('bubbles').appendChild(b); bubbles.set(c, b); }
  b.textContent = text; b.style.opacity = 1; b.until = performance.now() + dur * 1000;
}
const tmpV = new THREE.Vector3();
export function updateBubbles() {
  const now = performance.now();
  for (const [c, b] of bubbles) {
    if (now > b.until || !c.p.root.visible) { b.style.opacity = 0; continue; }
    c.p.root.getWorldPosition(tmpV); tmpV.y += 2.9; tmpV.project(camera);
    if (tmpV.z > 1) { b.style.opacity = 0; continue; }
    b.style.left = (tmpV.x * 0.5 + 0.5) * innerWidth + 'px';
    b.style.top = (-tmpV.y * 0.5 + 0.5) * innerHeight + 'px';
  }
}
