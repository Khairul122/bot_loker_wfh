// island, water, sky: clouds, stars, moon, birds, fireflies
import * as THREE from 'three';
import { scene } from '../core/engine.js';
import { mat, box, cyl, sph, group } from '../core/factory.js';
import { rand } from '../core/util.js';
import { rock } from './props.js';

export const water = new THREE.Mesh(new THREE.CircleGeometry(220, 48), mat(0x8fd3e8));
water.rotation.x = -Math.PI / 2; water.position.y = -0.6; scene.add(water);
export const island = cyl(52, 50, 1.2, 0x9fd28a, 0, -0.6, 0); island.castShadow = false;
cyl(50.2, 47, 2.4, 0xd9b48a, 0, -1.9, 0).castShadow = false;
// a sandy shore around the grass, rocks along it, and lighter patches that break up the lawn
const shore = new THREE.Mesh(new THREE.RingGeometry(48.2, 52.4, 64), mat(0xead2a4)); shore.rotation.x = -Math.PI / 2; shore.position.y = 0.012; scene.add(shore);
for (let k = 0; k < 26; k++) { const a = k / 26 * Math.PI * 2 + rand(-0.08, 0.08), r = rand(49.2, 51.6); rock(Math.cos(a) * r, Math.sin(a) * r, rand(0.7, 1.6)); }
for (const [x, z, r] of [[-40, 10, 5], [38, 20, 6], [-8, 34, 6], [12, -42, 4], [-36, -30, 4], [40, -24, 4]]) {
  const m = cyl(r, r, 0.02, 0xaedb98, x, 0.012, z, scene, { cast: false }); m.scale.z = 0.7;
}

export const clouds = [];
for (let i = 0; i < 9; i++) {
  const g = group(rand(-90, 90), rand(40, 58), rand(-80, 40));
  for (let k = 0; k < 4; k++) sph(rand(2.5, 4.5), 0xffffff, k * 3 - 4, rand(-0.8, 0.8), rand(-1, 1), g, { cast: false });
  g.userData.v = rand(0.6, 1.4); clouds.push(g);
}
// stars (night only)
const starGeo = new THREE.BufferGeometry();
const sp = []; for (let i = 0; i < 500; i++) { const a = rand(0, 6.28), b = rand(0.15, 1.4), r = 180; sp.push(r * Math.cos(b) * Math.cos(a), r * Math.sin(b), r * Math.cos(b) * Math.sin(a)); }
starGeo.setAttribute('position', new THREE.Float32BufferAttribute(sp, 3));
export const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xfff6d8, size: 1.3, fog: false }));
stars.visible = false; scene.add(stars);

export const birds = [];
for (let i = 0; i < 7; i++) {
  const b = group(0, 30, 0); b.userData = { o: i * 0.5, r: 38 + (i % 3) * 4 };
  for (const s of [-1, 1]) { const w = new THREE.Group(); w.position.x = s * 0.05; b.add(w); box(0.7, 0.04, 0.3, 0x4a4a5a, s * 0.35, 0, 0, w, { cast: false }); }
  birds.push(b);
}
export const ffBase = [];
const ffGeo = new THREE.BufferGeometry();
const ffPos = [];
for (let i = 0; i < 60; i++) { const v = new THREE.Vector3(rand(-40, -16), rand(0.6, 2.4), rand(-12, 16)); ffBase.push(v); ffPos.push(v.x, v.y, v.z); }
ffGeo.setAttribute('position', new THREE.Float32BufferAttribute(ffPos, 3));
export const fireflies = new THREE.Points(ffGeo, new THREE.PointsMaterial({ color: 0xfff27a, size: 0.35, transparent: true, opacity: 0.8, depthWrite: false }));
fireflies.visible = false; scene.add(fireflies);
export const moon = new THREE.Mesh(new THREE.SphereGeometry(6, 20, 14), new THREE.MeshBasicMaterial({ color: 0xfff6d8, fog: false }));
moon.position.set(-90, 95, -120); moon.visible = false; scene.add(moon);
