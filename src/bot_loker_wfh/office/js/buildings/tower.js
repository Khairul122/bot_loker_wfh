// the office tower: one floor per division, its room on top, and the glass lift shaft
import * as THREE from 'three';
import { scene } from '../core/engine.js';
import { gradient, box, tag } from '../core/factory.js';
import { FH, ROOF, ELEV_X } from '../core/util.js';
import { DIVS } from './divisions.js';
import { buildFloor } from './floor.js';
import lobi from './rooms/lobi.js';
import cari from './rooms/cari.js';
import seleksi from './rooms/seleksi.js';
import tulis from './rooms/tulis.js';
import lamar from './rooms/lamar.js';
import pantau from './rooms/pantau.js';
import freelance from './rooms/freelance.js';
import kantin from './rooms/kantin.js';
import owner from './rooms/owner.js';
import './rooftop.js';

const ROOMS = { lobi, cari, seleksi, tulis, lamar, pantau, freelance, kantin, owner };
DIVS.forEach((d, i) => ROOMS[d.id](buildFloor(i, d), d));

const shaft = new THREE.Mesh(new THREE.BoxGeometry(2.2, ROOF * FH + 1, 2.4), new THREE.MeshToonMaterial({ color: 0xbfe3f2, gradientMap: gradient, transparent: true, opacity: 0.28 }));
shaft.position.set(ELEV_X, (ROOF * FH + 1) / 2 - 0.4, 0); scene.add(shaft);
tag(shaft, { kind: 'spot', kindName: 'lift' });
for (let i = 0; i <= ROOF; i++) box(2.4, 0.15, 2.6, 0xffffff, ELEV_X, i * FH - 0.4, 0, scene, { cast: false });
