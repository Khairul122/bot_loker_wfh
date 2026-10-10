// ---------- team performance panel: application funnel + ranked employees ----------
import { derive } from '../data/stats.js';
import { DIVS } from '../buildings/divisions.js';
import { MOODS } from '../characters/body.js';
import { staff } from '../characters/team.js';
import { $, scoreColor, starsHtml, faceStyle } from './dom.js';
import { toggleReports } from './reports.js';

export let perfOpen = false;
export function renderPerf() {
  const d = derive();
  const steps = [['🔎', 'Ditemukan', d.total, '#7aa6d8'], ['✅', 'Lolos seleksi', d.cand, '#6bb38a'], ['📝', 'Draf lamaran', d.drafted, '#d98b5f'], ['🚀', 'Terkirim', d.sent, '#4ea7c4'], ['👀', 'Direspons', d.responded, '#b48ad8'], ['🎤', 'Interview', d.interview, '#d8738f'], ['🏆', 'Offer', d.offer, '#f2b84b']];
  const mx = Math.log10(Math.max(...steps.map(s => s[2]), 1) + 1);
  $('funnel').innerHTML = steps.map(([i, n, v, c]) => `<div class="step"><div class="bar" style="background:${c}33;height:${44 + 76 * Math.log10(v + 1) / mx}px;border:2px solid ${c}">${i}</div><b>${v}</b><small>${n}</small></div>`).join('');
  const ranked = [...staff].sort((a, b) => b.perfNow.score - a.perfNow.score);
  $('team').innerHTML = ranked.map((c, i) => `<button class="ecard" data-id="${c.def.id}">${i === 0 && c.perfNow.score > 0 ? '<span class="crown" title="Karyawan terbaik">👑</span>' : ''}
    <div class="face" style="${faceStyle(c)}">${MOODS[c.mood].emo}</div>
    <div style="flex:1;min-width:0"><div class="n">${c.name}</div><div class="r">${c.def.role}</div><div class="stars" style="font-size:14px">${starsHtml(c.perfNow.score)}</div>
    <div class="pills">${c.perfNow.pills.map(([ic, v]) => `<span class="pill">${ic} ${v}</span>`).join('')}</div></div>
    <div class="ring" style="--p:${Math.round(c.perfNow.score * 100)};--c:${scoreColor(c.perfNow.score)}"><div>${DIVS.find(x => x.id === c.def.div).icon}</div></div></button>`).join('');
  $('team').querySelectorAll('.ecard').forEach(b => b.onclick = () => { togglePerf(false); toggleReports(true, b.dataset.id); });
}
export function togglePerf(v = !perfOpen) { perfOpen = v; $('perf').classList.toggle('show', v); if (v) renderPerf(); }
$('bPerf').onclick = () => togglePerf();
$('perfClose').onclick = () => togglePerf(false);
$('perf').onclick = e => { if (e.target === $('perf')) togglePerf(false); };
