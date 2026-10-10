// Tegar · Resepsionis Telegram
import { store } from '../../core/store.js';
import { r01 } from '../../data/stats.js';

export default {
  id: 'tegar', name: 'Tegar', role: 'Resepsionis Telegram', div: 'lobi',
  look: { skin: 0xf1c9a5, hair: 0x3b2a20, shirt: 0x2aabee, pants: 0x3d4a66 },
  perf: d => ({ score: r01((store.S.history + d.drafted) / 12), pills: [['📨', store.S.history], ['⏳', d.pending]], lines: d.pending ? [`Ada ${d.pending} lamaran nunggu persetujuanmu`] : ['Semua pesan udah aku antar 📬'] }),
};
