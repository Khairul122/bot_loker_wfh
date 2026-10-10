// shared performance formulas for the hunters (one per job board / project source)
import { r01, sum, leadsBy } from '../../data/stats.js';

export function scout(src) {
  return d => { const j = d.jobs[src] || {}, f = sum(j), c = j.CANDIDATE || 0;
    return { score: f ? 0.5 * r01(f / 120) + 0.5 * r01(c / f / 0.1) : 0, pills: [['🔎', f], ['✅', c]],
      lines: f ? [`Udah ${f} lowongan aku intip!`, c ? `${c} yang cocok buat kamu ✨` : 'Belum nemu yang pas, lanjut cari!'] : ['Sumberku lagi sepi nih…'] }; };
}
export function leadScout(src, target) {
  return () => { const L = leadsBy(src), n = sum(L), i = L.INTERESTED || 0;
    return { score: n ? 0.5 * r01(n / target) + 0.5 * r01(i / n / 0.05) : 0, pills: [['📌', n], ['💛', i]],
      lines: n ? [`${n} proyek sudah aku kumpulkan`, i ? `${i} kamu tandai menarik 💛` : 'Cek kartuku, siapa tahu ada yang cocok'] : ['Aku belum mulai, suruh aku cari ya!'] }; };
}
