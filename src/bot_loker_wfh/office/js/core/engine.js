import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { $, toast } from '../ui/dom.js';

// ---------- renderer / scene ----------
// ask the browser for the discrete GPU; quality then adapts to the frame rate it actually gets
export const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
const maxRatio = Math.min(devicePixelRatio, 1.5);
renderer.setPixelRatio(maxRatio);
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
$('app').appendChild(renderer.domElement);

export const scene = new THREE.Scene();
scene.background = new THREE.Color(0xcfe9f5);
scene.fog = new THREE.Fog(0xcfe9f5, 90, 190);
export const camera = new THREE.PerspectiveCamera(42, innerWidth / innerHeight, 0.5, 400);
camera.position.set(40, 34, 52);
export const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 8, 0);
controls.enableDamping = true;
controls.maxPolarAngle = 1.42;
controls.minDistance = 9;
controls.maxDistance = 120;
export const clock = new THREE.Clock();

export const hemi = new THREE.HemisphereLight(0xfff4e0, 0x9cc48f, 1.5);
export const sun = new THREE.DirectionalLight(0xffe2b8, 2.3);
sun.position.set(35, 60, 25);
sun.castShadow = true;
sun.shadow.mapSize.set(1536, 1536);
renderer.shadowMap.autoUpdate = false; // redrawn every other frame in frame()
Object.assign(sun.shadow.camera, { left: -60, right: 60, top: 60, bottom: -60, near: 1, far: 160 });
sun.shadow.bias = -0.0004;
sun.shadow.normalBias = 0.04;
scene.add(hemi, sun);

addEventListener('resize', () => { camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); });

// ---------- light pool ----------
// ponytail: ~20 point lights cost fill-rate on weak GPUs; drop the lamp lights first if it stutters
// Every lamp and floor is a light *anchor*; only the LIGHT_POOL nearest the camera's focus get a real
// PointLight. A fixed light count keeps the toon shaders compiled once and the per-pixel cost flat.
const LIGHT_POOL = 6;
const lightAnchors = [];
export const lightPool = Array.from({ length: LIGHT_POOL }, () => { const l = new THREE.PointLight(0xffc982, 0, 13, 1.5); l.visible = false; scene.add(l); return l; });
export function light(x, y, z, color = 0xffc982, power = 14, dist = 13, parent = scene) {
  lightAnchors.push({ local: new THREE.Vector3(x, y, z), parent, color, power, dist, p: null });
}
let lightT = 0;
export const resetLights = () => { lightT = 0; };
export function updateLightPool(dt, focus, night) {
  if (!night || (lightT -= dt) > 0) return;
  lightT = 0.4;
  for (const a of lightAnchors) if (!a.p) { a.parent.updateWorldMatrix(true, false); a.p = a.local.clone().applyMatrix4(a.parent.matrixWorld); }
  const near = [...lightAnchors].sort((a, b) => a.p.distanceToSquared(focus) - b.p.distanceToSquared(focus));
  const n = quality ? LIGHT_POOL : 3; // low quality keeps the count (no recompile) but darkens half
  lightPool.forEach((l, i) => { const a = near[i]; if (!a) return; l.position.copy(a.p); l.color.set(a.color); l.power = i < n ? a.power : 0; l.distance = a.dist; });
}

// ---------- adaptive quality: step down until ~45 fps, step back up when there is headroom ----------
let fpsAcc = 0, fpsN = 0, quality = 2;
export function adaptQuality(dt) {
  fpsAcc += dt; fpsN++;
  if (fpsAcc < 3) return;
  const fps = fpsN / fpsAcc; fpsAcc = fpsN = 0;
  if (fps < 42 && quality > 0) setQuality(quality - 1);
  else if (fps > 58 && quality < 2) setQuality(quality + 1);
}
function setQuality(q) {
  quality = q;
  renderer.setPixelRatio(q === 2 ? maxRatio : q === 1 ? Math.min(maxRatio, 1.15) : 0.85);
  lightT = 0;
}
// a software renderer (no GPU) cannot keep up: say so once and start at the lowest setting
(() => {
  const gl = renderer.getContext(), ext = gl.getExtension('WEBGL_debug_renderer_info');
  const name = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : '';
  if (/swiftshader|llvmpipe|basic render|software/i.test(name)) {
    setQuality(0);
    setTimeout(() => toast('⚠️ Browser tidak memakai GPU. Aktifkan "Gunakan akselerasi grafis" di pengaturan browser lalu buka ulang'), 2500);
  }
})();
