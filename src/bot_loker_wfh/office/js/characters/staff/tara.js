// Tara · Pemantau Status
import { store } from '../../core/store.js';
import { r01 } from '../../data/stats.js';

export default {
  id: 'tara', name: 'Tara', role: 'Pemantau Status', div: 'pantau',
  look: { skin: 0xe8b98f, hair: 0x5a3020, shirt: 0xd8738f, pants: 0x3d4a66, bun: 1 },
  perf: d => ({ score: d.sent ? 0.4 * r01(store.S.history / 10) + 0.6 * r01(d.responded / d.sent) : 0, pills: [['👀', d.responded], ['📬', d.sent]], lines: d.responded ? [`${d.responded} perusahaan udah respons!`] : ['Sabar ya, aku pantau terus 👀'] }),
};
