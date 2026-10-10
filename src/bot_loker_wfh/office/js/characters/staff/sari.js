// Sari · Penilai Skill
import { r01 } from '../../data/stats.js';

export default {
  id: 'sari', name: 'Sari', role: 'Penilai Skill', div: 'seleksi',
  look: { skin: 0xe8b98f, hair: 0x2b211c, shirt: 0x8a86d8, pants: 0x4a4a5a, bun: 1 },
  perf: d => ({ score: d.total ? 0.6 * d.processed / d.total + 0.4 * r01(d.cand / 20) : 0, pills: [['🧮', d.processed], ['⏳', d.disc]], lines: d.disc ? [`Masih ${d.disc} antrean buat dinilai`] : ['Semua lowongan udah aku nilai!'] }),
};
