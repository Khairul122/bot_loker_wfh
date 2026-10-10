// ---------- leisure spots: places a character can sit, play or rest ----------
// pose: sit | swing | play | shoot | lie | dance | stand | floor | eat | wash
import { tag } from '../core/factory.js';
import { ROOF } from '../core/util.js';
import '../buildings/tower.js'; // builds the rooms that fill roomSpots
import { roomSpots } from '../buildings/floor.js';
import { hammock, parasol } from '../buildings/rooftop.js';
import { benchA, benchB, benchC, picnic, pond, kiosk } from './park.js';
import { hoop, ball, swingFrame, swings, slide, ping } from './arena.js';

export const spots = [
  { kind: 'bench', level: 0, x: -24.5, z: 2.95, ry: Math.PI, pose: 'sit', obj: benchA, emo: '😌', energy: 6 },
  { kind: 'bench', level: 0, x: -23.4, z: 2.95, ry: Math.PI, pose: 'sit', obj: benchA, emo: '😌', energy: 6 },
  { kind: 'bench', level: 0, x: -36, z: 6, ry: Math.PI * 0.75, pose: 'sit', obj: benchB, emo: '🍃', energy: 6 },
  { kind: 'bench', level: 0, x: -22, z: -14, ry: 0.2, pose: 'sit', obj: benchC, emo: '🐦', energy: 6 },
  { kind: 'picnic', level: 0, x: -30.6, z: 11.5, ry: 0.4, pose: 'floor', obj: picnic, emo: '🧺', energy: 5, joy: 2 },
  { kind: 'picnic', level: 0, x: -29.4, z: 11.2, ry: -0.6, pose: 'floor', obj: picnic, emo: '🍉', energy: 5, joy: 2 },
  { kind: 'pond', level: 0, x: -24.3, z: -4, ry: -Math.PI / 2, pose: 'stand', obj: pond, emo: '🦆', joy: 3 },
  { kind: 'swing', level: 0, swing: swings[0], ry: 0, pose: 'swing', obj: swingFrame, emo: '🎶', joy: 5 },
  { kind: 'swing', level: 0, swing: swings[1], ry: 0, pose: 'swing', obj: swingFrame, emo: '😆', joy: 5 },
  { kind: 'hoop', level: 0, x: 28, z: -7, ry: Math.PI, pose: 'shoot', obj: hoop, emo: '🏀', joy: 4, energy: -2 },
  { kind: 'ping', level: 0, x: 32.3, z: 4, ry: Math.PI / 2, pose: 'play', obj: ping, emo: '🏓', joy: 4, energy: -2 },
  { kind: 'ping', level: 0, x: 35.7, z: 4, ry: -Math.PI / 2, pose: 'play', obj: ping, emo: '🏓', joy: 4, energy: -2 },
  { kind: 'slide', level: 0, x: 24.2, z: 7, ry: Math.PI / 2, pose: 'dance', obj: slide, emo: '🛝', joy: 4, energy: -1 },
  { kind: 'kafe', level: 0, x: -12, z: 17.6, ry: Math.PI, pose: 'stand', obj: kiosk, emo: '☕', energy: 12 },
  { kind: 'kopi', level: 0, x: 6.8, z: -0.6, ry: Math.PI, pose: 'stand', obj: null, emo: '☕', energy: 10 },
  { kind: 'hammock', level: ROOF, x: -3.9, z: 2.5, ry: Math.PI / 2, pose: 'lie', obj: hammock, emo: '😴', energy: 10 },
  { kind: 'parasol', level: ROOF, x: 4, z: 3.6, ry: Math.PI, pose: 'floor', obj: parasol, emo: '🌤️', energy: 6, joy: 2 },
  { kind: 'sofa', level: 0, x: -5.6, z: 3, ry: Math.PI / 2, pose: 'sit', obj: null, emo: '🛋️', energy: 6 },
  { kind: 'sofa', level: 3, x: -5, z: 3.6, ry: 0, pose: 'sit', obj: null, emo: '📚', energy: 6 },
  ...roomSpots,
];
spots.forEach((s, i) => { s.id = i; s.by = null; if (s.obj) tag(s.obj, { kind: 'spot', kindName: s.kind }); });
tag(ball, { kind: 'spot', kindName: 'hoop' });
