// Lulu · Asisten AI
import { store } from '../../core/store.js';
import { sum } from '../../data/stats.js';

export default {
  id: 'lulu', name: 'Lulu', role: 'Asisten AI', div: 'tulis',
  look: { skin: 0xdfe6f0, hair: 0x6bc4c4, shirt: 0xffffff, pants: 0x6bc4c4 },
  perf: () => { const ok = (store.S.llm || {}).success || 0, n = sum(store.S.llm); return { score: n ? 0.4 + 0.6 * ok / n : 0.15, pills: [['🤖', n], ['✅', ok]], lines: n ? [`${ok} dari ${n} tugas lancar`] : ['Aku lagi istirahat, pakai template dulu 😴'], sad: n > 3 && ok / n < 0.5 }; },
};
