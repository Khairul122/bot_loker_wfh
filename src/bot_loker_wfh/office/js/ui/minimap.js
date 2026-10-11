// ---------- Bully-style Radar Minimap with Real-time Coordinates & Staff Blips ----------
import { staff } from '../characters/team.js';
import { me } from '../characters/player.js';
import { DIVS } from '../buildings/divisions.js';
import { ROOF } from '../core/util.js';
import { $ } from './dom.js';

let canvas, ctx;
const RADAR_RADIUS = 70; // canvas half-size / radar radius
const WORLD_RANGE = 42; // visible world range in units

export function initMinimap() {
  canvas = $('radarCanvas');
  if (!canvas) return;
  ctx = canvas.getContext('2d');
}

export function updateMinimap(t) {
  if (!ctx || !canvas) return;

  const w = canvas.width, h = canvas.height;
  const cx = w / 2, cy = h / 2;

  ctx.clearRect(0, 0, w, h);

  const px = me.pos.x;
  const pz = me.pos.z;

  // 1. Radar Circular Mask & Base Background
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, RADAR_RADIUS, 0, Math.PI * 2);
  ctx.clip();

  // Dark Radar Grid Base
  ctx.fillStyle = '#0f172a';
  ctx.fillRect(0, 0, w, h);

  // Radar Concentric Rings
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.arc(cx, cy, RADAR_RADIUS * 0.45, 0, Math.PI * 2);
  ctx.arc(cx, cy, RADAR_RADIUS * 0.85, 0, Math.PI * 2);
  ctx.stroke();

  // Convert World Coordinates (wx, wz) to Radar Canvas Pixels (rx, ry)
  const toRadar = (wx, wz) => {
    const rx = cx + ((wx - px) / WORLD_RANGE) * RADAR_RADIUS;
    const ry = cy + ((wz - pz) / WORLD_RANGE) * RADAR_RADIUS;
    return { rx, ry };
  };

  // 2. Draw World Layout Map Features
  // 2a. Kolam Bebek (-30, -6, radius 6)
  const pondPt = toRadar(-30, -6);
  ctx.fillStyle = '#38bdf8';
  ctx.beginPath();
  ctx.arc(pondPt.rx, pondPt.ry, (6 / WORLD_RANGE) * RADAR_RADIUS, 0, Math.PI * 2);
  ctx.fill();

  // 2b. Gedung Utama (-9 to 9, -6 to 6)
  const bldgTL = toRadar(-9, -6);
  const bldgBR = toRadar(9, 6);
  ctx.fillStyle = 'rgba(241, 245, 249, 0.22)';
  ctx.strokeStyle = '#94a3b8';
  ctx.lineWidth = 1;
  ctx.fillRect(bldgTL.rx, bldgTL.ry, bldgBR.rx - bldgTL.rx, bldgBR.ry - bldgTL.ry);
  ctx.strokeRect(bldgTL.rx, bldgTL.ry, bldgBR.rx - bldgTL.rx, bldgBR.ry - bldgTL.ry);

  // 2c. Area Taman (-36 to 36, -35 to -18)
  const parkTL = toRadar(-36, -35);
  const parkBR = toRadar(36, -18);
  ctx.fillStyle = 'rgba(34, 197, 94, 0.16)';
  ctx.fillRect(parkTL.rx, parkTL.ry, parkBR.rx - parkTL.rx, parkBR.ry - parkTL.ry);

  // 3. Draw Staff / Employee Blips with Initials & Color Badges
  staff.forEach(c => {
    const pt = toRadar(c.pos.x, c.pos.z);
    const dFromCenter = Math.hypot(pt.rx - cx, pt.ry - cy);

    let drawX = pt.rx;
    let drawY = pt.ry;

    // Pin out-of-bounds blips to radar perimeter (Bully/GTA radar style)
    if (dFromCenter > RADAR_RADIUS - 9) {
      const angle = Math.atan2(pt.ry - cy, pt.rx - cx);
      drawX = cx + Math.cos(angle) * (RADAR_RADIUS - 9);
      drawY = cy + Math.sin(angle) * (RADAR_RADIUS - 9);
    }

    // Outer Circle
    ctx.beginPath();
    ctx.arc(drawX, drawY, 6.5, 0, Math.PI * 2);
    ctx.fillStyle = c.look?.shirt || '#3b82f6';
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Staff Initials
    const initial = (c.name || 'S').slice(0, 1).toUpperCase();
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 8px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(initial, drawX, drawY);
  });

  ctx.restore();

  // 4. Draw Center Player (Owner) Blip with Direction Cone
  ctx.save();
  ctx.translate(cx, cy);

  const playerYaw = me.ry || 0;
  ctx.rotate(-playerYaw);

  // Field of View Cone
  ctx.fillStyle = 'rgba(240, 138, 93, 0.35)';
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(-10, -22);
  ctx.lineTo(10, -22);
  ctx.closePath();
  ctx.fill();

  // Player Center Dot
  ctx.beginPath();
  ctx.arc(0, 0, 5, 0, Math.PI * 2);
  ctx.fillStyle = '#f08a5d';
  ctx.fill();
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.restore();

  // 5. Live Coordinates & Location Text Update
  const coordEl = $('radarCoords');
  const locEl = $('radarLocation');
  if (coordEl) {
    coordEl.textContent = `X: ${Math.round(px)} | Z: ${Math.round(pz)}`;
  }
  if (locEl) {
    locEl.textContent = getLocationName(px, pz, me.level);
  }
}

function getLocationName(x, z, level) {
  const distToPond = Math.hypot(x - (-30), z - (-6));
  if (distToPond < 6.2) return 'Kolam Bebek 🦆';
  if (level === ROOF) return 'Taman Atap 🌿';
  if (x >= -9 && x <= 9 && z >= -6 && z <= 6) {
    const div = DIVS[level];
    return div ? `${div.name} (Lt ${level + 1})` : `Gedung Kantor (Lt ${level + 1})`;
  }
  if (z < -18) return 'Taman Terbuka 🌳';
  if (z >= -16 && z <= -8) return 'Komplek Rumah 🏘️';
  if (z > 18) return 'Arena Bermain 🏀';
  if (x < -10 && z >= 10) return 'Kafe Santai ☕';
  return 'Halaman Kantor 🏢';
}
