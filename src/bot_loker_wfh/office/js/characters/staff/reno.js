// Reno · Pemburu RemoteOK
import { scout } from './perf.js';

export default {
  id: 'reno', name: 'Reno', role: 'Pemburu RemoteOK', div: 'cari',
  look: { skin: 0xe0ac7e, hair: 0x1f1a17, shirt: 0x6bb38a, pants: 0x4a4a5a },
  hunt: { src: 'remoteok', site: 'RemoteOK', what: 'lowongan' },
  perf: scout('remoteok'),
};
