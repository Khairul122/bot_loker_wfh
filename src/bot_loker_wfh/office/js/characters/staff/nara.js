// Nara · Pemburu Projects.co.id 🏠
import { leadScout } from './perf.js';

export default {
  id: 'nara', name: 'Nara', role: 'Pemburu Projects.co.id 🏠', div: 'freelance',
  look: { skin: 0xe0ac7e, hair: 0x2b211c, shirt: 0xef6a5a, pants: 0x4a4a5a, bun: 1 },
  hunt: { src: 'projects.co.id', site: 'Projects.co.id', what: 'proyek' },
  perf: leadScout('projects.co.id', 30),
};
