import * as THREE from 'three';

export const rand = (a, b) => a + Math.random() * (b - a);
export const pick = a => a[Math.floor(Math.random() * a.length)];
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const V = (x, z) => new THREE.Vector3(x, 0, z);
export const today = () => new Date().toDateString();
