// Bimo · Eksekutor Penawaran 🤝
import { r01 } from '../../data/stats.js';

export default {
  id: 'bimo', name: 'Bimo', role: 'Eksekutor Penawaran 🤝', div: 'freelance',
  look: { skin: 0xe0ac7e, hair: 0x1f1a17, shirt: 0x2563eb, pants: 0x334155 },
  perf: d => ({ score: 0.5 * r01((d.proposals || 0) / 3) + 0.5 * r01((d.leads || 0) / 5), pills: [['🤝', d.proposals || 0], ['📌', d.leads || 0]], lines: (d.proposals || 0) ? [`${d.proposals} penawaran proyek siap diajukan 🤝`] : ['Siap bantu ajukan penawaran proyek freelance!'] }),
};
