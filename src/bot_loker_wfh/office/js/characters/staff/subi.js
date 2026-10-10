// Subi · Pengirim Lamaran
import { r01 } from '../../data/stats.js';

export default {
  id: 'subi', name: 'Subi', role: 'Pengirim Lamaran', div: 'lamar',
  look: { skin: 0xf1c9a5, hair: 0x3b2a20, shirt: 0xef6a5a, pants: 0x4a4a5a },
  perf: d => ({ score: 0.8 * r01(d.sent / 5) + (d.failed ? 0 : 0.2 * (d.sent ? 1 : 0)), pills: [['🚀', d.sent], ['⚠️', d.failed]], lines: d.sent ? [`${d.sent} lamaran udah terbang 🚀`] : ['Belum ada yang dikirim'], sad: d.failed > d.sent }),
};
