import { scene } from '../core/engine.js';
import { box, group, sign, walkables } from '../core/factory.js';
import { D, FH, W, V } from '../core/util.js';
import { ROOM_WALLS } from '../world/navigation.js';
import { roomSpots } from './floor.js';
import { placeAnnexContents } from '../domain/world-layout.js';

const WALL_HEIGHT = FH - 0.4;
const DOOR_WIDTH = 2.8;

export function buildAnnex({ id, name, icon, accent, floorColor, wallColor, x, z, room, ownerOnly = false }) {
  const root = group(x, 0, z, scene);
  root.userData.buildingId = id;
  const slab = box(W + 0.8, 0.4, D + 0.8, floorColor, 0, -0.18, 0, root, { cast: false });
  box(W + 0.8, WALL_HEIGHT, 0.3, wallColor, 0, WALL_HEIGHT / 2, -D / 2 - 0.25, root);
  box(0.3, WALL_HEIGHT, D + 0.8, wallColor, -W / 2 - 0.25, WALL_HEIGHT / 2, 0, root);
  box(0.3, WALL_HEIGHT, D + 0.8, wallColor, W / 2 + 0.25, WALL_HEIGHT / 2, 0, root);

  const frontWidth = (W - DOOR_WIDTH) / 2;
  for (const side of [-1, 1]) {
    box(frontWidth, WALL_HEIGHT, 0.3, wallColor, side * (DOOR_WIDTH / 2 + frontWidth / 2), WALL_HEIGHT / 2, D / 2 + 0.25, root);
    box(1.7, 1.35, 0.06, 0xbfe3f2, side * 5.3, 2.0, D / 2 + 0.08, root, { cast: false });
  }
  for (const wx of [-5.4, -2.7, 0, 2.7, 5.4]) {
    box(1.7, 1.25, 0.06, 0xbfe3f2, wx, 2.05, -D / 2 - 0.08, root, { cast: false });
  }
  box(W + 1, 0.18, D + 1, accent, 0, FH - 0.04, 0, root, { cast: false });
  box(3.6, 0.16, 2.3, accent, 0, FH + 0.08, D / 2 + 0.65, root, { cast: false });
  const accentHex = `#${accent.toString(16).padStart(6, '0')}`;
  sign(icon, name, accentHex, '#ffffff', 0, 3.05, D / 2 + 0.42, root, 7.5);

  const spotStart = roomSpots.length;
  const wallStart = ROOM_WALLS.length;
  room(root);

  const layout = {
    x, z, level: 0, ownerOnly,
    footprint: { width: W, depth: D },
  };
  placeAnnexContents(roomSpots.slice(spotStart), ROOM_WALLS.slice(wallStart), layout);

  const entry = [V(x, z + D / 2 + 1.2), V(x, z + D / 2 - 0.8)];
  const boxBounds = [x - W / 2, x + W / 2, z - D / 2, z + D / 2];
  walkables.push({ mesh: slab, level: 0, via: entry, box: boxBounds });
  ROOM_WALLS.push(
    [x - W / 2 - 0.5, x + W / 2 + 0.5, z - D / 2 - 0.5, z - D / 2, 0],
    [x - W / 2 - 0.5, x - W / 2, z - D / 2 - 0.5, z + D / 2 + 0.5, 0],
    [x + W / 2, x + W / 2 + 0.5, z - D / 2 - 0.5, z + D / 2 + 0.5, 0],
    [x - W / 2 - 0.5, x - DOOR_WIDTH / 2, z + D / 2, z + D / 2 + 0.5, 0],
    [x + DOOR_WIDTH / 2, x + W / 2 + 0.5, z + D / 2, z + D / 2 + 0.5, 0],
  );
  return root;
}
