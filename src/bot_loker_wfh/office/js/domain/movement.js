const MAX_COLLISION_STEP = 0.08;

export function advancePosition(from, target, distance, canMove) {
  const end = { x: from.x, z: from.z };
  let remaining = Math.max(0, distance);

  while (remaining > 0) {
    const dx = target.x - end.x;
    const dz = target.z - end.z;
    const length = Math.hypot(dx, dz);
    if (length < 0.001) break;

    const step = Math.min(remaining, length, MAX_COLLISION_STEP);
    const next = { x: end.x + dx / length * step, z: end.z + dz / length * step };
    if (canMove(end, next)) {
      end.x = next.x;
      end.z = next.z;
    } else {
      const alongX = { x: next.x, z: end.z };
      const alongZ = { x: end.x, z: next.z };
      if (canMove(end, alongX)) end.x = alongX.x;
      else if (canMove(end, alongZ)) end.z = alongZ.z;
    }
    remaining -= step;
  }

  return end;
}
