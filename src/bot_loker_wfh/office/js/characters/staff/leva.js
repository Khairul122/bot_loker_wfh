// Leva · Pemburu Lever
import { scout } from './perf.js';

export default {
  id: 'leva', name: 'Leva', role: 'Pemburu Lever', div: 'cari',
  look: { skin: 0xf1c9a5, hair: 0xd9a05b, shirt: 0x7aa6d8, pants: 0x4a4a5a, bun: 1 },
  hunt: { src: 'lever', site: 'Lever', what: 'lowongan' },
  perf: scout('lever'),
};
