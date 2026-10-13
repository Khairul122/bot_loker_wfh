// A building shell from a plan: walls (with windows or glass), door frames and leaves that open for
// anyone close by. Shared by the office and the rumah susun.
import * as THREE from 'three';
import { add, mat, box, sph, group, sign } from '../core/factory.js';
import { wallPieces } from '../domain/office-plan.js';
import { addWall } from '../world/navigation.js';

const C = { outer: 0xf4ece2, inner: 0xfbf7f1, trim: 0x3f4a5a, frame: 0x55606e, wood: 0x9a6b4a };
export const glass = mat(0xbfe3f2, { p: { transparent: true, opacity: 0.28, depthWrite: false } });

// A box spanning heights y0..y1 whose origin sits on the floor, so scaling y shrinks it in place.
export function piece(w, y0, y1, d, color, x, z, parent, o = {}) {
  const geo = new THREE.BoxGeometry(w, y1 - y0, d); geo.translate(0, (y0 + y1) / 2, 0);
  return add(geo, color, x, 0, z, parent, o);
}

// b = { root, upper (group hidden in the cutaway), cut: [] shrunk in it, doors: [] animated ones }
export function buildShell(b, { lines, doors, rooms, height: H, thickness: T = 0.3 }) {
  const shrinking = (w, y0, y1, d, color, x, z, o) => { const m = piece(w, y0, y1, d, color, x, z, b.root, o); b.cut.push(m); return m; };
  // where inner walls meet an outer wall: no window there, a mullion on a glass facade
  const junctions = lines.filter(l => l.kind === 'interior' || l.kind === 'glass').flatMap(l => [[l.x0, l.z0], [l.x1, l.z1]]);
  const nearJunction = (p, along) => junctions.some(([x, z]) => p.alongX
    ? Math.abs(z - p.rect[2] - T / 2) < 0.01 && Math.abs(x - along) < 1.3
    : Math.abs(x - p.rect[0] - T / 2) < 0.01 && Math.abs(z - along) < 1.3);

  function outerWall(p, w, d, x, z, len, windows) {
    shrinking(w, 0, H, d, p.color ?? C.outer, x, z);
    piece(w + 0.02, H - 0.28, H + 0.02, d + 0.04, C.trim, x, z, b.upper, { cast: false });
    if (!windows) return;
    const n = Math.floor(len / 3.2);
    for (let k = 0; k < n; k++) {
      const along = (p.alongX ? p.rect[0] : p.rect[2]) + (k + 0.5) * (len / n);
      if (nearJunction(p, along)) continue;
      const [wx, wz] = p.alongX ? [along, z] : [x, along];
      box(p.alongX ? 1.9 : T + 0.06, 1.35, p.alongX ? T + 0.06 : 1.9, 0xbfe3f2, wx, 1.75, wz, b.upper, { glow: 0xffd89a, cast: false });
      box(p.alongX ? 2.1 : T + 0.12, 0.08, p.alongX ? T + 0.12 : 2.1, C.trim, wx, 1.04, wz, b.upper, { cast: false });
    }
  }
  function glassWall(p, w, d, x, z, len, base, top) {
    shrinking(w, 0, base, d, p.kind === 'facade' ? p.color ?? C.outer : C.frame, x, z);
    shrinking(p.alongX ? w : 0.06, base, top, p.alongX ? 0.06 : d, 0, x, z, { material: glass, cast: false });
    const n = Math.max(1, Math.round(len / 1.6));
    for (let k = 0; k <= n; k++) {
      const along = (p.alongX ? p.rect[0] : p.rect[2]) + k * (len / n);
      const [mx, mz] = p.alongX ? [along, z] : [x, along];
      shrinking(p.alongX ? 0.08 : d, base, top, p.alongX ? d : 0.08, C.frame, mx, mz, { cast: false });
    }
    piece(w, top - 0.1, top, d + 0.02, C.frame, x, z, b.upper, { cast: false });
  }

  function doorway(d, kind) {
    const w = d.width, ry = d.axis === 'x' ? 0 : -Math.PI / 2;
    const joined = Object.values(rooms).filter(r => d.to.includes(r.id));
    const inside = joined.find(r => !r.hall) || joined[0];
    // the room's side of the door in the door's own frame (local +x runs along the wall)
    const rx = (inside.x0 + inside.x1) / 2 - d.x, rz = (inside.z0 + inside.z1) / 2 - d.z;
    const roomSide = Math.sign(d.axis === 'x' ? rz : -rx) || 1;
    const frame = group(d.x, 0, d.z, b.root, ry); b.cut.push(frame);
    const head = group(d.x, 0, d.z, b.upper, ry);
    const flat = group(d.x, 0, d.z, b.root, ry);
    const outer = kind !== 'interior' && kind !== 'glass';
    for (const s of [-1, 1]) box(0.12, 2.4, T + 0.06, C.frame, s * (w / 2 - 0.06), 1.2, 0, frame);
    piece(w, 2.4, H - (outer ? 0 : 0.02), T, outer ? C.outer : C.inner, 0, 0, head);
    box(w, 0.12, T + 0.06, C.frame, 0, 2.4, 0, head, { cast: false });
    box(w, 0.02, T + 0.2, 0xb9ae9f, 0, 0.035, 0, flat, { cast: false }); // threshold
    box(w * 0.75, 0.02, 0.7, d.to.includes('out') ? 0x8a6b55 : 0x6b7b8f, 0, 0.04, -roomSide * 0.75, flat, { cast: false }); // doormat outside the room
    if (!d.to.includes('out')) sign(inside.icon, inside.name, '#3f4a5a', '#fff', 0, 2.78, -roomSide * (T / 2 + 0.02), head, Math.min(2.4, w + 0.6)).rotation.y = roomSide > 0 ? Math.PI : 0;

    const door = { x: d.x, z: d.z, u: 0, set: null };
    if (d.style === 'slide') {
      const off = -roomSide * (T / 2 + 0.06), half = (w - 0.24) / 2;
      const leaves = [-1, 1].map(s => {
        const leaf = group(s * half / 2 + s * 0.06, 0, off, frame);
        box(half, 2.3, 0.05, 0, 0, 1.15, 0, leaf, { material: glass, cast: false });
        for (const e of [-1, 1]) box(0.06, 2.3, 0.07, C.frame, e * half / 2, 1.15, 0, leaf, { cast: false });
        box(half, 0.08, 0.07, C.frame, 0, 2.27, 0, leaf, { cast: false });
        return { leaf, s, x: leaf.position.x };
      });
      door.set = u => leaves.forEach(l => { l.leaf.position.x = l.x + l.s * u * half * 0.95; });
    } else {
      const hinge = group(-w / 2 + 0.12, 0, 0, frame), lw = w - 0.26;
      if (d.style === 'glass') {
        box(lw, 2.3, 0.05, 0, lw / 2, 1.15, 0, hinge, { material: glass, cast: false });
        box(lw, 0.1, 0.07, C.frame, lw / 2, 2.25, 0, hinge, { cast: false });
      } else {
        box(lw, 2.3, 0.06, d.color ?? (outer ? C.wood : 0xd9c3a5), lw / 2, 1.15, 0, hinge);
        box(lw * 0.6, 0.6, 0.07, 0xbfe3f2, lw / 2, 1.65, 0, hinge, { cast: false });
      }
      sph(0.05, 0xd4b062, lw - 0.12, 1.05, 0.06 * roomSide, hinge, { cast: false });
      door.set = u => { hinge.rotation.y = roomSide * 1.45 * u; };
    }
    b.doors.push(door);
  }

  for (const p of wallPieces(lines, doors, T)) {
    const [x0, x1, z0, z1] = p.rect, w = x1 - x0, d = z1 - z0, x = (x0 + x1) / 2, z = (z0 + z1) / 2;
    const len = p.alongX ? w : d;
    if (p.door) { doorway(p.door, p.kind); continue; }
    addWall(p.rect);
    if (p.kind === 'exterior' || p.kind === 'plain') outerWall(p, w, d, x, z, len, p.kind === 'exterior');
    else if (p.kind === 'facade') glassWall(p, w, d, x, z, len, 0.55, H);
    else if (p.kind === 'glass') glassWall(p, w, d, x, z, len, 0.9, H - 0.02);
    else shrinking(w, 0, H - 0.02, d, p.color ?? C.inner, x, z);
  }
}
