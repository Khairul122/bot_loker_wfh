// the owner's office: executive desk with the report tray, a standing KPI screen, a sofa corner
import * as THREE from 'three';
import { box, cyl, sph, group, tag } from '../../core/factory.js';
import { store } from '../../core/store.js';
import { rand, V } from '../../core/util.js';
import { chair, sofa, shelf, rug, plant, screens } from '../../world/props.js';
import { solid, spot, toWorld } from '../registry.js';

export const DELIVER_AT = []; // where reports are handed over, in world space
export const reportStack = [];
const kpiBoard = { canvas: null, tex: null };

export default function build(g) {
  rug(-1.5, 0.3, 2.4, 0xb5651d, g);
  const dk = group(-1.5, 0, -1.2, g);
  box(3.4, 0.12, 1.4, 0x6b4a33, 0, 0.8, 0, dk); box(3.2, 0.74, 0.1, 0x5a3d2b, 0, 0.4, 0.62, dk);
  for (const x of [-1.6, 1.6]) box(0.12, 0.8, 1.3, 0x5a3d2b, x, 0.4, 0, dk);
  box(1.2, 0.7, 0.06, 0x3b3b48, -0.4, 1.25, -0.35, dk);
  screens.push(box(1.1, 0.6, 0.02, 0x9fe6ff, -0.4, 1.25, -0.315, dk, { glow: 0x9fe6ff, unique: true, cast: false }));
  box(0.7, 0.06, 0.5, 0x8a6b55, 1.1, 0.89, 0.15, dk); // report tray: one paper per unreviewed report
  for (let k = 0; k < 12; k++) { const p = box(0.55, 0.035, 0.4, k % 2 ? 0xffffff : 0xfff6e0, 1.1, 0.94 + k * 0.04, 0.15, dk, { cast: false }); p.rotation.y = rand(-0.2, 0.2); p.visible = false; reportStack.push(p); }
  sph(0.08, 0xffd166, -1.3, 0.95, 0.3, dk);
  tag(dk, { kind: 'spot', kindName: 'owner' }); solid(g, -1.5, -1.2, 3.4, 1.4);
  const oc = chair(-1.5, -2.05, 0, g, 0x5a3d2b); oc.scale.setScalar(1.2); tag(oc, { kind: 'spot', kindName: 'owner' });
  spot(g, { kind: 'owner', x: -1.5, z: -2.05, ry: 0, pose: 'sit', emo: '👑', energy: 3, ownerOnly: true });
  for (const x of [-3.7, 0.7]) chair(x, 0.5, Math.PI, g, 0xd8b48a);
  for (const [x, z] of [[-2.4, 0.45], [-1.5, 0.55], [-0.6, 0.45]]) { const p = toWorld(g, x, z); DELIVER_AT.push(V(p.x, p.z)); }

  tag(sofa(-4.9, 2.2, Math.PI / 2, g, 0x7a5a8a), { kind: 'spot', kindName: 'sofa' }); solid(g, -4.9, 2.2, 2.4, 0.9, Math.PI / 2);
  box(0.8, 0.4, 1.4, 0x6b4a33, -3.6, 0.2, 2.2, g); solid(g, -3.6, 2.2, 0.8, 1.4);
  spot(g, { kind: 'sofa', x: -4.8, z: 2.2, ry: Math.PI / 2, pose: 'sit', emo: '🛋️', energy: 6, ownerOnly: true });
  shelf(-4.6, -3.5, 0, g); solid(g, -4.6, -3.5, 2, 0.5);
  // the owner's own coffee corner
  const bar = group(5.5, 0, 0.8, g);
  box(0.7, 1, 1.6, 0x6b4a33, 0, 0.5, 0, bar); box(0.4, 0.55, 0.4, 0x3b3b48, 0, 1.28, -0.3, bar); cyl(0.07, 0.07, 0.12, 0xffffff, 0, 1.06, 0.4, bar);
  tag(bar, { kind: 'spot', kindName: 'kopi' }); solid(g, 5.5, 0.8, 0.7, 1.6);
  spot(g, { kind: 'kopi', x: 4.7, z: 0.8, ry: Math.PI / 2, pose: 'stand', emo: '☕', energy: 10, ownerOnly: true });
  plant(5.3, 3.3, g, 1.2); plant(0.9, -3.4, g); solid(g, 5.3, 3.3, 0.8, 0.8); solid(g, 0.9, -3.4, 0.7, 0.7);

  // standing KPI screen: real team scores, redrawn after every stats poll
  const st = group(3.6, 0, -3.1, g);
  for (const s of [-1, 1]) box(0.1, 2.5, 0.1, 0x3f4a5a, s * 1.8, 1.25, 0, st);
  box(3.8, 2, 0.1, 0x3f4a5a, 0, 1.55, 0, st);
  kpiBoard.canvas = document.createElement('canvas'); kpiBoard.canvas.width = 1024; kpiBoard.canvas.height = 512;
  kpiBoard.tex = new THREE.CanvasTexture(kpiBoard.canvas); kpiBoard.tex.colorSpace = THREE.SRGBColorSpace;
  const board = new THREE.Mesh(new THREE.PlaneGeometry(3.6, 1.8), new THREE.MeshBasicMaterial({ map: kpiBoard.tex }));
  board.position.set(0, 1.55, 0.06); st.add(board);
  tag(st, { kind: 'spot', kindName: 'owner' }); solid(g, 3.6, -3.1, 3.8, 0.3);
}

// each employee's real score and the owner's average rating
export function drawKpi(staff) {
  if (!kpiBoard.canvas || !staff.length) return;
  const g = kpiBoard.canvas.getContext('2d');
  g.fillStyle = '#fffaf2'; g.fillRect(0, 0, 1024, 512);
  g.fillStyle = '#4a3426'; g.font = '900 34px Nunito, sans-serif'; g.textBaseline = 'middle';
  g.fillText(`📊 Papan Kinerja Tim${store.live ? '' : ' (data contoh)'}`, 24, 30);
  staff.forEach((c, i) => {
    const col = Math.floor(i / 10), row = i % 10, x = 24 + col * 500, y = 74 + row * 43;
    const s = c.perfNow?.score || 0, rt = store.desk.ratings[c.def.id];
    g.fillStyle = '#4a3426'; g.font = '800 24px Nunito, sans-serif'; g.fillText(c.name, x, y);
    g.fillStyle = '#f1e2cf'; g.beginPath(); g.roundRect(x + 100, y - 13, 260, 26, 13); g.fill();
    g.fillStyle = s >= 0.6 ? '#5cb87a' : s >= 0.4 ? '#f2b84b' : s >= 0.2 ? '#ef8a6b' : '#a9b4c8';
    g.beginPath(); g.roundRect(x + 100, y - 13, Math.max(26, 260 * s), 26, 13); g.fill();
    g.fillStyle = '#8a6b55'; g.font = '800 20px Nunito, sans-serif'; g.fillText(rt ? `★ ${rt.avg.toFixed(1)}` : '★ –', x + 372, y);
  });
  kpiBoard.tex.needsUpdate = true;
}
