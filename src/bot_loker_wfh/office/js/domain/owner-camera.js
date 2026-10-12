export function ownerCameraPose({ x, y, z }) {
  return {
    position: { x: x + 22, y: y + 18, z: z + 28 },
    target: { x, y: y + 1.2, z },
  };
}

export function overviewCameraPose() {
  return {
    position: { x: 3, y: 76, z: 82 },
    target: { x: 3, y: 4, z: 0 },
  };
}
