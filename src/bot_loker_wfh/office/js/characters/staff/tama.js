// Tama · Pengintai Telegram 🏠
import { leadScout } from './perf.js';

export default {
  id: 'tama', name: 'Tama', role: 'Pengintai Telegram 🏠', div: 'freelance',
  look: { skin: 0xc68a5e, hair: 0x1f1a17, shirt: 0x2aabee, pants: 0x3d3d4a },
  hunt: { src: 'telegram', site: 'channel Telegram', what: 'proyek' },
  perf: leadScout('telegram', 30),
};
