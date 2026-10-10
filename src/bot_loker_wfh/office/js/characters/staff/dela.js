// Dela · Pemburu Dealls
import { scout } from './perf.js';

export default {
  id: 'dela', name: 'Dela', role: 'Pemburu Dealls', div: 'cari',
  look: { skin: 0xf5d0b0, hair: 0x5a3020, shirt: 0xb48ad8, pants: 0x3d3d4a, bun: 1 },
  hunt: { src: 'dealls', site: 'Dealls', what: 'lowongan' },
  perf: scout('dealls'),
};
