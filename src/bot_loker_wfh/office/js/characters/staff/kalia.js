// Kalia · Pemburu Kalibrr
import { scout } from './perf.js';

export default {
  id: 'kalia', name: 'Kalia', role: 'Pemburu Kalibrr', div: 'cari',
  look: { skin: 0xe0ac7e, hair: 0x1f1a17, shirt: 0xef8a6b, pants: 0x3d4a66, bun: 1 },
  hunt: { src: 'kalibrr', site: 'Kalibrr', what: 'lowongan' },
  perf: scout('kalibrr'),
};
