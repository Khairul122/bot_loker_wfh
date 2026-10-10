// Gery · Pemburu Greenhouse
import { scout } from './perf.js';

export default {
  id: 'gery', name: 'Gery', role: 'Pemburu Greenhouse', div: 'cari',
  look: { skin: 0xc68a5e, hair: 0x2b211c, shirt: 0x4c9a6a, pants: 0x3d3d4a },
  hunt: { src: 'greenhouse', site: 'Greenhouse', what: 'lowongan' },
  perf: scout('greenhouse'),
};
