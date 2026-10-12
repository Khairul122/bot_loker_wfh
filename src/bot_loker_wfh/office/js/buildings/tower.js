// the office tower: one floor per division, its room on top, and the glass lift shaft
import * as THREE from 'three';
import { scene } from '../core/engine.js';
import { gradient, box, tag } from '../core/factory.js';
import { FH, ROOF, ELEV_X } from '../core/util.js';
import { DIVS } from './divisions.js';
import { buildFloor } from './floor.js';
import { buildAnnex } from './annex.js';
import lobi from './rooms/lobi.js';
import cari from './rooms/cari.js';
import seleksi from './rooms/seleksi.js';
import tulis from './rooms/tulis.js';
import lamar from './rooms/lamar.js';
import pantau from './rooms/pantau.js';
import freelance from './rooms/freelance.js';
import kantin from './rooms/kantin.js';
import owner, { DELIVER_AT } from './rooms/owner.js';
import rapat from './rooms/rapat.js';
import './rooftop.js';

const ROOMS = { lobi, cari, seleksi, tulis, lamar, pantau, freelance, kantin, owner, rapat };
DIVS.forEach((d, i) => {
  ROOMS[d.id](buildFloor(i, d), d);
});

// Keep the one-storey support buildings on the far side of the tower so the
// first view stays focused on the seven-floor office instead of roof slabs.
const ownerOrigin = { x: -22, z: -30 };
const meetingOrigin = { x: 0, z: -30 };
const canteenOrigin = { x: 22, z: -30 };

export const ownerBuilding = buildAnnex({
  id: 'owner', name: 'Ruang Owner', icon: '👑', accent: 0x8a6b55,
  floorColor: 0xe3d3bd, wallColor: 0xf7efe3, ...ownerOrigin, room: owner, ownerOnly: true,
});
export const meetingBuilding = buildAnnex({
  id: 'meeting', name: 'Ruang Rapat', icon: '💬', accent: 0x5b9bd5,
  floorColor: 0xd4e6f1, wallColor: 0xe8f0f7, ...meetingOrigin, room: rapat,
});
export const canteenBuilding = buildAnnex({
  id: 'canteen', name: 'Kantin & Toilet', icon: '🍜', accent: 0xe0844a,
  floorColor: 0xf3e3c8, wallColor: 0xfff8ec, ...canteenOrigin, room: kantin,
});

DELIVER_AT.forEach(point => { point.x += ownerOrigin.x; point.z += ownerOrigin.z; });

export const shaft = new THREE.Mesh(new THREE.BoxGeometry(2.2, ROOF * FH + 1, 2.4), new THREE.MeshToonMaterial({ color: 0xbfe3f2, gradientMap: gradient, transparent: true, opacity: 0.28 }));
shaft.position.set(ELEV_X, (ROOF * FH + 1) / 2 - 0.4, 0); scene.add(shaft);
tag(shaft, { kind: 'spot', kindName: 'lift' });
export const landings = [];
for (let i = 0; i <= ROOF; i++) landings.push(box(2.4, 0.15, 2.6, 0xffffff, ELEV_X, i * FH - 0.4, 0, scene, { cast: false }));
