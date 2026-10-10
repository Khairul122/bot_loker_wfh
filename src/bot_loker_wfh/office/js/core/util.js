import * as THREE from 'three';

// building dimensions: floor height, width, depth, number of floors (= DIVS.length), rooftop level
export const FH = 4.2, W = 18, D = 12, NF = 10, ROOF = NF;
export const ELEV_X = 10.9, DOOR_X = 9.0;

export const rand = (a, b) => a + Math.random() * (b - a);
export const pick = a => a[Math.floor(Math.random() * a.length)];
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const V = (x, z) => new THREE.Vector3(x, 0, z);
export const today = () => new Date().toDateString();
