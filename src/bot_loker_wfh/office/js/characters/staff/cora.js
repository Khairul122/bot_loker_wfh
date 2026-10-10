// Cora · Penulis Surat Lamaran
import { r01 } from '../../data/stats.js';

export default {
  id: 'cora', name: 'Cora', role: 'Penulis Surat Lamaran', div: 'tulis',
  look: { skin: 0xf5d0b0, hair: 0xa0522d, shirt: 0xd98b5f, pants: 0x4a4a5a, bun: 1 },
  perf: d => ({ score: d.cand ? r01(d.drafted / Math.max(3, d.cand * 0.4)) : 0, pills: [['📝', d.drafted], ['📥', d.cand]], lines: d.drafted < d.cand ? ['Kasih aku lowongan buat ditulis dong ✍️', `${d.cand} kandidat siap aku buatin surat`] : ['Surat lamaran beres semua!'] }),
};
