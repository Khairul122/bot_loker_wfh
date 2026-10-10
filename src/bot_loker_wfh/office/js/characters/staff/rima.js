// Rima · Pemburu Remotive
import { scout } from './perf.js';

export default {
  id: 'rima', name: 'Rima', role: 'Pemburu Remotive', div: 'cari',
  look: { skin: 0xf5d0b0, hair: 0x7a3e2a, shirt: 0xf2b84b, pants: 0x5a4a7a, bun: 1 },
  hunt: { src: 'remotive', site: 'Remotive', what: 'lowongan' },
  perf: scout('remotive'),
};
