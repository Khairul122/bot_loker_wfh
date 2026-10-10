// level 8: the owner's office, report tray and the live KPI board
import * as THREE from 'three';
import { box, sph, group, tag } from '../../core/factory.js';
import { store } from '../../core/store.js';
import { rand, V, W } from '../../core/util.js';
import { chair, sofa, shelf, rug, plant, screens } from '../../world/props.js';
import { OWNER } from '../divisions.js';
import { roomSpots } from '../floor.js';

const DESK = { x: -2, z: -2.7 };
export const DELIVER_AT = [V(-2.9, -1.1), V(-2, -1.0), V(-1.1, -1.1)]; // where reports are handed over
export const reportStack = [];
const kpiBoard = { canvas: null, tex: null };

export default function build(g) {
  rug(-2, -1.5, 3.4, 0xb5651d, g);
  const dk = group(DESK.x, 0, DESK.z, g);
  box(3.4, 0.12, 1.4, 0x6b4a33, 0, 0.8, 0, dk); box(3.2, 0.74, 0.1, 0x5a3d2b, 0, 0.4, 0.62, dk);
  for (const x of [-1.6, 1.6]) box(0.12, 0.8, 1.3, 0x5a3d2b, x, 0.4, 0, dk);
  box(1.2, 0.7, 0.06, 0x3b3b48, -0.4, 1.25, -0.35, dk);
  screens.push(box(1.1, 0.6, 0.02, 0x9fe6ff, -0.4, 1.25, -0.315, dk, { glow: 0x9fe6ff, unique: true, cast: false }));
  box(0.7, 0.06, 0.5, 0x8a6b55, 1.1, 0.89, 0.15, dk); // report tray: one paper per unreviewed report
  for (let k = 0; k < 12; k++) { const p = box(0.55, 0.035, 0.4, k % 2 ? 0xffffff : 0xfff6e0, 1.1, 0.94 + k * 0.04, 0.15, dk, { cast: false }); p.rotation.y = rand(-0.2, 0.2); p.visible = false; reportStack.push(p); }
  sph(0.08, 0xffd166, -1.3, 0.95, 0.3, dk);
  tag(dk, { kind: 'spot', kindName: 'owner' });
  const oc = chair(DESK.x, DESK.z - 0.9, 0, g, 0x5a3d2b); oc.scale.setScalar(1.2); tag(oc, { kind: 'spot', kindName: 'owner' });
  roomSpots.push({ kind: 'owner', level: OWNER, x: DESK.x, z: DESK.z - 0.85, ry: 0, pose: 'sit', emo: '👑', energy: 3 });
  for (const x of [-3.3, -0.7]) chair(x, -0.2, Math.PI, g, 0xd8b48a);
  sofa(4.6, 3.6, Math.PI, g, 0x7a5a8a); box(1.6, 0.4, 0.8, 0x6b4a33, 4.6, 0.2, 2.2, g);
  roomSpots.push({ kind: 'sofa', level: OWNER, x: 4.6, z: 3.5, ry: Math.PI, pose: 'sit', emo: '🛋️', energy: 6 });
  shelf(5.4, -5.5, 0, g); shelf(7.6, -5.5, 0, g);
  plant(-8.2, -5, g, 1.4); plant(8.2, 5.2, g, 1.2); plant(-8.2, 5.2, g);
  // KPI board on the left wall: real team scores, redrawn after every stats poll
  kpiBoard.canvas = document.createElement('canvas'); kpiBoard.canvas.width = 1024; kpiBoard.canvas.height = 512;
  kpiBoard.tex = new THREE.CanvasTexture(kpiBoard.canvas); kpiBoard.tex.colorSpace = THREE.SRGBColorSpace;
  const board = new THREE.Mesh(new THREE.PlaneGeometry(5.6, 2.8), new THREE.MeshBasicMaterial({ map: kpiBoard.tex }));
  board.position.set(-W / 2 + 0.08, 2.1, 1.2); board.rotation.y = Math.PI / 2; g.add(board);
  box(0.06, 3, 5.8, 0x5a3d2b, -W / 2 + 0.03, 2.1, 1.2, g, { cast: false });
  tag(board, { kind: 'spot', kindName: 'owner' });
}

// each employee's real score and the owner's average rating
export function drawKpi(staff) {
  if (!kpiBoard.canvas || !staff.length) return;
  const g = kpiBoard.canvas.getContext('2d');
  g.fillStyle = '#fffaf2'; g.fillRect(0, 0, 1024, 512);
  g.fillStyle = '#4a3426'; g.font = '900 34px Nunito, sans-serif'; g.textBaseline = 'middle';
  g.fillText(`📊 Papan Kinerja Tim${store.live ? '' : ' (data contoh)'}`, 24, 30);
  staff.forEach((c, i) => {
    const col = i < 9 ? 0 : 1, row = i % 9, x = 24 + col * 500, y = 78 + row * 47;
    const s = c.perfNow?.score || 0, rt = store.desk.ratings[c.def.id];
    g.fillStyle = '#4a3426'; g.font = '800 24px Nunito, sans-serif'; g.fillText(c.name, x, y);
    g.fillStyle = '#f1e2cf'; g.beginPath(); g.roundRect(x + 100, y - 13, 260, 26, 13); g.fill();
    g.fillStyle = s >= 0.6 ? '#5cb87a' : s >= 0.4 ? '#f2b84b' : s >= 0.2 ? '#ef8a6b' : '#a9b4c8';
    g.beginPath(); g.roundRect(x + 100, y - 13, Math.max(26, 260 * s), 26, 13); g.fill();
    g.fillStyle = '#8a6b55'; g.font = '800 20px Nunito, sans-serif'; g.fillText(rt ? `★ ${rt.avg.toFixed(1)}` : '★ –', x + 372, y);
  });
  kpiBoard.tex.needsUpdate = true;
}
