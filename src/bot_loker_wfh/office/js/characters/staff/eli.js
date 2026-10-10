// Eli · Penjaga Kelayakan
import { r01 } from '../../data/stats.js';

export default {
  id: 'eli', name: 'Eli', role: 'Penjaga Kelayakan', div: 'seleksi',
  look: { skin: 0xc68a5e, hair: 0x3b2a20, shirt: 0x5a7ab8, pants: 0x3d3d4a },
  perf: d => ({ score: d.total ? 0.5 * r01(d.processed / 200) + 0.5 * r01(d.cand / 20) : 0, pills: [['🚫', d.filtered], ['✅', d.cand]], lines: [`${d.cand} lolos, ${d.filtered} aku saring`, 'Yang nggak remote aku buang 🙅'] }),
};
