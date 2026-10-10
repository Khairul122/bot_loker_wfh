// ---------- camera: follow the owner, building overview, owner POV (first person) ----------
import * as THREE from 'three';
import { camera, controls } from '../core/engine.js';
import { store } from '../core/store.js';
import { me, ring } from '../characters/player.js';
import { $, toast } from '../ui/dom.js';

const tmpV = new THREE.Vector3();
export function updateCamera(dt) {
  if (store.fp) {
    if (me.path.length && me.walking) { const d = me.targetRy - store.yaw; store.yaw += Math.atan2(Math.sin(d), Math.cos(d)) * Math.min(1, dt * 4); }
    const { yaw, pitch } = store;
    me.ry = me.targetRy = yaw;
    me.p.head.getWorldPosition(tmpV);
    camera.position.set(tmpV.x + Math.sin(yaw) * 0.12, tmpV.y + 0.08, tmpV.z + Math.cos(yaw) * 0.12);
    camera.lookAt(camera.position.x + Math.sin(yaw) * Math.cos(pitch), camera.position.y + Math.sin(pitch), camera.position.z + Math.cos(yaw) * Math.cos(pitch));
    return;
  }
  const want = store.overview ? new THREE.Vector3(3, 15, -6) : new THREE.Vector3(me.pos.x, me.y + 1.2, me.pos.z);
  const delta = want.sub(controls.target).multiplyScalar(Math.min(1, dt * 3));
  controls.target.add(delta); camera.position.add(delta);
  if (store.overview && camera.position.distanceTo(controls.target) < 50) camera.position.addScaledVector(camera.position.clone().sub(controls.target).normalize(), dt * 30);
}

export function setFP(v) {
  store.fp = v; store.overview = false;
  controls.enabled = !v;
  me.p.body.visible = !v; me.bubble.visible = !v; ring.visible = !v;
  camera.fov = v ? 72 : 42; camera.near = v ? 0.05 : 0.5; camera.updateProjectionMatrix();
  $('bPov').classList.toggle('on', v); $('cross').style.display = v ? 'block' : 'none';
  if (v) { store.yaw = me.ry; store.pitch = -0.05; toast('👁️ Mode POV: geser mouse untuk melihat · WASD jalan · klik / E untuk menyapa · V keluar'); }
  else {
    camera.position.set(me.pos.x + 22, me.y + 18, me.pos.z + 28);
    controls.target.set(me.pos.x, me.y + 1.2, me.pos.z);
  }
}
$('bPov').onclick = () => setFP(!store.fp);
