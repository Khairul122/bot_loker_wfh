const DEFAULT_FOOTPRINT = Object.freeze({ width: 18, depth: 12 });

function translatePoint(point, x, z) {
  point.x += x;
  point.z += z;
}

export function placeAnnexContents(spots, walls, { x, z, level = 0, ownerOnly = false, footprint = DEFAULT_FOOTPRINT }) {
  const entry = [
    { x, z: z + footprint.depth / 2 + 1.2 },
    { x, z: z + footprint.depth / 2 - 0.8 },
  ];
  const bounds = [
    x - footprint.width / 2,
    x + footprint.width / 2,
    z - footprint.depth / 2,
    z + footprint.depth / 2,
  ];

  for (const spot of spots) {
    spot.x += x;
    spot.z += z;
    spot.level = level;
    spot.via = [...entry, ...(spot.via || []).map(point => {
      translatePoint(point, x, z);
      return point;
    })];
    spot.box = spot.box
      ? [spot.box[0] + x, spot.box[1] + x, spot.box[2] + z, spot.box[3] + z]
      : bounds;
    if (ownerOnly) spot.ownerOnly = true;
  }

  for (const wall of walls) {
    wall[0] += x;
    wall[1] += x;
    wall[2] += z;
    wall[3] += z;
    wall[4] = level;
  }
  return { spots, walls };
}
