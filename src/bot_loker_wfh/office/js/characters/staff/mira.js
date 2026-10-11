// Mira · Manajer Proyek Freelance 🧑‍💼: owns the freelance division and reports its results to the owner
import { leadsBy, r01, sum } from '../../data/stats.js';

export default {
  id: 'mira', name: 'Mira', role: 'Manajer Proyek Freelance 🧑‍💼', div: 'freelance',
  look: { skin: 0xe8b894, hair: 0x2b1d2f, shirt: 0x7c3aed, pants: 0x2f2a4a },
  perf: () => {
    const L = leadsBy(), sent = L.SUBMITTED || 0, total = sum(L), waiting = (L.INTERESTED || 0) + (L.APPROVED || 0);
    return {
      score: 0.45 * r01(sent / 3) + 0.3 * r01(total / 50) + 0.25 * (waiting ? 0.6 : 1),
      pills: [['🚀', sent], ['📌', total]],
      lines: sent ? [`${sent} bid freelance sudah terkirim 🚀`, 'Klik Profil untuk laporan divisi'] : ['Aku pantau divisi freelance dan lapor ke kamu 🧑‍💼'],
    };
  },
};
