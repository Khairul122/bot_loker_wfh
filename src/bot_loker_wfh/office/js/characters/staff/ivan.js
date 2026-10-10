// Ivan · Pelatih Interview
import { r01 } from '../../data/stats.js';

export default {
  id: 'ivan', name: 'Ivan', role: 'Pelatih Interview', div: 'pantau',
  look: { skin: 0xc68a5e, hair: 0x2b211c, shirt: 0x6b5a8a, pants: 0x3d3d4a },
  perf: d => ({ score: d.interview ? r01(0.6 + 0.15 * d.interview + 0.4 * d.offer) : (d.sent ? 0.3 : 0.1), pills: [['🎤', d.interview], ['🏆', d.offer]], lines: d.offer ? ['ADA OFFER!! 🎉🎉'] : d.interview ? ['Yuk latihan interview bareng aku!'] : ['Siap latihan kapan aja 💪'] }),
};
