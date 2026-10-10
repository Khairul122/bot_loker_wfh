// reusable 3D building blocks: cached toon materials, primitives, emoji/sign textures, click registry
import * as THREE from 'three';
import { scene } from './engine.js';
import './fonts.js';

export const gradient = new THREE.DataTexture(new Uint8Array([110, 185, 255]), 3, 1, THREE.RedFormat);
gradient.minFilter = gradient.magFilter = THREE.NearestFilter;
gradient.needsUpdate = true;
const matCache = new Map();
export const glow = []; // materials that light up at night
export function mat(color, opts = {}) {
  const key = color + JSON.stringify(opts);
  if (!opts.unique && matCache.has(key)) return matCache.get(key);
  const m = new THREE.MeshToonMaterial({ color, gradientMap: gradient, ...opts.p });
  if (opts.glow) { m.emissive = new THREE.Color(opts.glow); m.emissiveIntensity = 0; glow.push(m); }
  if (!opts.unique) matCache.set(key, m);
  return m;
}
export function add(geo, color, x, y, z, parent = scene, o = {}) {
  const m = new THREE.Mesh(geo, o.material || mat(color, o));
  m.position.set(x, y, z);
  if (!geo.boundingSphere) geo.computeBoundingSphere();
  m.castShadow = o.cast !== false && geo.boundingSphere.radius > 0.3;
  m.receiveShadow = true;
  parent.add(m);
  return m;
}
export const box = (w, h, d, c, x, y, z, p, o) => add(new THREE.BoxGeometry(w, h, d), c, x, y, z, p, o);
export const cyl = (rt, rb, h, c, x, y, z, p, o) => add(new THREE.CylinderGeometry(rt, rb, h, 18), c, x, y, z, p, o);
export const sph = (r, c, x, y, z, p, o) => add(new THREE.SphereGeometry(r, 18, 14), c, x, y, z, p, o);
export function group(x = 0, y = 0, z = 0, parent = scene, ry = 0) {
  const g = new THREE.Group(); g.position.set(x, y, z); g.rotation.y = ry; parent.add(g); return g;
}

// emoji / text textures
const texCache = new Map();
export function emojiTex(e, bubble = true) {
  const key = e + bubble;
  if (texCache.has(key)) return texCache.get(key);
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d');
  if (bubble) { g.fillStyle = '#fff'; g.beginPath(); g.arc(64, 60, 52, 0, 7); g.fill(); g.beginPath(); g.moveTo(52, 104); g.lineTo(64, 124); g.lineTo(76, 104); g.fill(); }
  g.font = `${bubble ? 64 : 96}px "Segoe UI Emoji","Apple Color Emoji","Noto Color Emoji",sans-serif`;
  g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(e, 64, bubble ? 64 : 70);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  texCache.set(key, t); return t;
}
function signTex(icon, text, bg, fg) {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 192;
  const g = c.getContext('2d');
  g.fillStyle = bg; g.beginPath(); g.roundRect(8, 8, 1008, 176, 70); g.fill();
  g.fillStyle = fg; g.font = '900 88px Nunito, sans-serif'; g.textBaseline = 'middle';
  g.font = '96px "Segoe UI Emoji","Apple Color Emoji",sans-serif'; g.fillText(icon, 50, 100);
  g.font = '900 80px Nunito, sans-serif'; g.fillText(text, 180, 100);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
export function sign(icon, text, bg, fg, x, y, z, parent, w = 7) {
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, w * 0.1875), new THREE.MeshBasicMaterial({ map: signTex(icon, text, bg, fg), transparent: true }));
  m.position.set(x, y, z); parent.add(m); return m;
}

// ---------- registries ----------
export const clickables = []; // meshes with userData.{kind,...}
export function tag(obj, data) { obj.traverse(o => { if (o.isMesh) { o.userData = { ...o.userData, ...data }; clickables.push(o); } }); }
export const walkables = []; // {mesh, level}
export const animated = []; // per-frame callbacks (t, dt)
