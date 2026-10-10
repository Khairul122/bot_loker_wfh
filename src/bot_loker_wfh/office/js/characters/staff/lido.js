// Lido · Pemburu Freelancer.com 🌍
import { leadScout } from './perf.js';

export default {
  id: 'lido', name: 'Lido', role: 'Pemburu Freelancer.com 🌍', div: 'freelance',
  look: { skin: 0xf1c9a5, hair: 0xd9a05b, shirt: 0xc9a227, pants: 0x4a4a5a },
  hunt: { src: 'freelancer', site: 'Freelancer.com', what: 'proyek' },
  perf: leadScout('freelancer', 200),
};
