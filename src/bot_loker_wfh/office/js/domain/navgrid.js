// Walking routes: an occupancy grid over the island, A* between free cells, then string-pulled into
// straight legs. Walls and furniture are axis-aligned rects [x0, x1, z0, z1].
export const inRect = (x, z, r, m = 0) => x > r[0] - m && x < r[1] + m && z > r[2] - m && z < r[3] + m;

// does segment a-b touch rect r grown by m? (slab test)
export function segmentHitsRect(ax, az, bx, bz, r, m = 0) {
  let t0 = 0, t1 = 1;
  for (const [p, d, lo, hi] of [[ax, bx - ax, r[0] - m, r[1] + m], [az, bz - az, r[2] - m, r[3] + m]]) {
    if (Math.abs(d) < 1e-12) {
      if (p <= lo || p >= hi) return false;
      continue;
    }
    let u0 = (lo - p) / d, u1 = (hi - p) / d;
    if (u0 > u1) [u0, u1] = [u1, u0];
    t0 = Math.max(t0, u0); t1 = Math.min(t1, u1);
    if (t0 >= t1) return false;
  }
  return true;
}

// radius: how far cell centres keep from any rect; clearance: how far straightened legs keep.
// Both stay above the 0.25 m collision margin so a planned route never grinds along a wall.
export function createNavGrid({ bounds, walls, solids = [], cell = 0.5, radius = 0.45, clearance = 0.3, open = () => true }) {
  const [minX, maxX, minZ, maxZ] = bounds;
  const cols = Math.ceil((maxX - minX) / cell), rows = Math.ceil((maxZ - minZ) / cell);
  const blocked = new Uint8Array(cols * rows);
  const cx = i => minX + (i + 0.5) * cell, cz = j => minZ + (j + 0.5) * cell;
  for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) if (!open(cx(i), cz(j))) blocked[j * cols + i] = 1;
  const all = [...walls, ...solids];
  for (const r of all) {
    const i0 = Math.max(0, Math.floor((r[0] - radius - minX) / cell)), i1 = Math.min(cols - 1, Math.floor((r[1] + radius - minX) / cell));
    const j0 = Math.max(0, Math.floor((r[2] - radius - minZ) / cell)), j1 = Math.min(rows - 1, Math.floor((r[3] + radius - minZ) / cell));
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) if (inRect(cx(i), cz(j), r, radius)) blocked[j * cols + i] = 1;
  }
  const free = (i, j) => i >= 0 && j >= 0 && i < cols && j < rows && !blocked[j * cols + i];
  const wallClear = (a, b) => !walls.some(r => segmentHitsRect(a.x, a.z, b.x, b.z, r));
  const clear = (a, b) => !all.some(r => segmentHitsRect(a.x, a.z, b.x, b.z, r, clearance));

  // the closest free cell reachable from p without crossing a wall (never the room next door)
  function nearestFree(p, maxRing = 16) {
    const ci = Math.floor((p.x - minX) / cell), cj = Math.floor((p.z - minZ) / cell);
    let best = null, bestD = Infinity, foundRing = Infinity;
    for (let ring = 0; ring <= Math.min(maxRing, foundRing + 1); ring++) {
      for (let j = cj - ring; j <= cj + ring; j++) for (let i = ci - ring; i <= ci + ring; i++) {
        if (Math.max(Math.abs(i - ci), Math.abs(j - cj)) !== ring || !free(i, j)) continue;
        const q = { x: cx(i), z: cz(j) };
        const d = Math.hypot(q.x - p.x, q.z - p.z);
        if (d < bestD && wallClear(p, q)) { best = { i, j, ...q }; bestD = d; foundRing = Math.min(foundRing, ring); }
      }
    }
    return best;
  }

  function astar(s, g) {
    const n = cols * rows, start = s.j * cols + s.i, goal = g.j * cols + g.i;
    const cost = new Float64Array(n).fill(Infinity), came = new Int32Array(n).fill(-1), done = new Uint8Array(n);
    const heap = [], fs = [];
    const push = (k, f) => {
      let i = heap.length; heap.push(k); fs.push(f);
      while (i > 0) { const p = (i - 1) >> 1; if (fs[p] <= f) break; heap[i] = heap[p]; fs[i] = fs[p]; i = p; }
      heap[i] = k; fs[i] = f;
    };
    const pop = () => {
      const top = heap[0], k = heap.pop(), f = fs.pop();
      if (heap.length) {
        let i = 0;
        for (;;) {
          const l = 2 * i + 1, r = l + 1;
          let m = i, mf = f;
          if (l < heap.length && fs[l] < mf) { m = l; mf = fs[l]; }
          if (r < heap.length && fs[r] < mf) { m = r; mf = fs[r]; }
          if (m === i) break;
          heap[i] = heap[m]; fs[i] = fs[m]; i = m;
        }
        heap[i] = k; fs[i] = f;
      }
      return top;
    };
    const h = k => { const dx = Math.abs(k % cols - g.i), dz = Math.abs(Math.floor(k / cols) - g.j); return Math.max(dx, dz) + (Math.SQRT2 - 1) * Math.min(dx, dz); };
    cost[start] = 0; push(start, h(start));
    while (heap.length) {
      const k = pop();
      if (k === goal) break;
      if (done[k]) continue;
      done[k] = 1;
      const i = k % cols, j = Math.floor(k / cols);
      for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) {
        if (!di && !dj) continue;
        if (!free(i + di, j + dj)) continue;
        if (di && dj && (!free(i + di, j) || !free(i, j + dj))) continue; // no squeezing past a corner
        const nk = k + dj * cols + di, c = cost[k] + (di && dj ? Math.SQRT2 : 1);
        if (c < cost[nk]) { cost[nk] = c; came[nk] = k; push(nk, c + h(nk)); }
      }
    }
    if (cost[goal] === Infinity) return null;
    const cells = [];
    for (let k = goal; k !== -1; k = came[k]) cells.push(k);
    return cells.reverse();
  }

  // every free cell reachable from s (same 8-neighbour moves as astar)
  function flood(s) {
    const seen = new Uint8Array(cols * rows), queue = new Int32Array(cols * rows);
    let head = 0, tail = 0;
    seen[s.j * cols + s.i] = 1; queue[tail++] = s.j * cols + s.i;
    while (head < tail) {
      const k = queue[head++], i = k % cols, j = Math.floor(k / cols);
      for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) {
        if ((!di && !dj) || !free(i + di, j + dj)) continue;
        if (di && dj && (!free(i + di, j) || !free(i, j + dj))) continue;
        const nk = k + dj * cols + di;
        if (!seen[nk]) { seen[nk] = 1; queue[tail++] = nk; }
      }
    }
    return seen;
  }

  // The reachable cell to stop at for `to`: close to it, on its side of any wall, and when `prefer`
  // (a unit vector) is given, on that side of it (a sofa is entered from the front, a desk chair from behind).
  function goalFor(reach, to, prefer) {
    const ci = Math.floor((to.x - minX) / cell), cj = Math.floor((to.z - minZ) / cell), R = Math.ceil(4 / cell);
    let best = null, bestScore = Infinity;
    for (let j = cj - R; j <= cj + R; j++) for (let i = ci - R; i <= ci + R; i++) {
      if (i < 0 || j < 0 || i >= cols || j >= rows || !reach[j * cols + i]) continue;
      const q = { i, j, x: cx(i), z: cz(j) }, dx = q.x - to.x, dz = q.z - to.z;
      const score = Math.hypot(dx, dz) + (prefer && dx * prefer.x + dz * prefer.z < 0 ? 1.5 : 0);
      if (score < bestScore && wallClear(q, to)) { best = q; bestScore = score; }
    }
    if (best) return { ...best, onSide: true };
    let far = null, farD = Infinity; // boxed in: settle for the nearest floor that can be reached
    for (let k = 0; k < reach.length; k++) {
      if (!reach[k]) continue;
      const x = cx(k % cols), z = cz(Math.floor(k / cols)), d = Math.hypot(x - to.x, z - to.z);
      if (d < farD) { farD = d; far = { i: k % cols, j: Math.floor(k / cols), x, z }; }
    }
    return far && { ...far, onSide: false };
  }

  // Waypoints from `from` toward `to` (excluding `from`). The walk ends on reachable floor next to `to`;
  // with `exact` it then steps onto `to` itself, unless a wall is in the way. null if `from` is boxed in.
  function findPath(from, to, { exact = false, prefer = null } = {}) {
    const s = nearestFree(from);
    if (!s) return null;
    const g = goalFor(flood(s), to, prefer);
    const cells = g && astar(s, g);
    if (!cells) return null;
    const pts = [from, ...cells.map(k => ({ x: cx(k % cols), z: cz(Math.floor(k / cols)) }))];
    const out = [];
    for (let a = 0; a < pts.length - 1;) {
      let b = a + 1;
      while (b + 1 < pts.length && clear(pts[a], pts[b + 1])) b++;
      out.push(pts[b]); a = b;
    }
    if (exact && g.onSide) out.push({ x: to.x, z: to.z });
    return out;
  }

  const isFree = p => free(Math.floor((p.x - minX) / cell), Math.floor((p.z - minZ) / cell));
  return { findPath, nearestFree, isFree, clear, wallClear };
}
