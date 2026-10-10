// Faris · Pengisi Formulir
import { store } from '../../core/store.js';
import { sum } from '../../data/stats.js';

export default {
  id: 'faris', name: 'Faris', role: 'Pengisi Formulir', div: 'lamar',
  look: { skin: 0xe0ac7e, hair: 0x1f1a17, shirt: 0x4ea7c4, pants: 0x3d3d4a },
  perf: d => { const n = sum(store.S.forms), ok = (store.S.forms || {}).filled || 0; return { score: n ? 0.3 + 0.7 * ok / n : (d.sent ? 0.4 : 0.1), pills: [['🧾', n], ['✅', ok]], lines: n ? [`${ok} formulir terisi rapi`] : ['Belum ada formulir hari ini'], sad: n > 2 && ok / n < 0.4 }; },
};
