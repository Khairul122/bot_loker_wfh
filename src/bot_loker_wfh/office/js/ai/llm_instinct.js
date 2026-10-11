// ---------- LLM-Driven Autonomous AI & Instinct Engine for Staff Exploration ----------
import { spots } from '../world/spots.js';
import { staff } from '../characters/team.js';
import { me } from '../characters/player.js';
import { say } from '../fx/bubbles.js';
import { sendTo, goBack } from './routine.js';
import { pick, rand, ROOF } from '../core/util.js';
import { DIVS } from '../buildings/divisions.js';

// LLM Endpoint Configuration (Supports Supabase Edge Functions, Groq, Ollama, or OpenAI)
const LLM_CONFIG = {
  endpoint: '/api/staff-instinct', // Can be hooked to local server or Supabase Edge Function
  active: true,
};

// All available exploration zones across floors & outdoor
export const EXPLORE_ZONES = [
  { name: 'Kolam Bebek 🦆', filter: s => s.kind === 'pond' },
  { name: 'Taman Atap / Rooftop Garden 🌿', filter: s => s.level === ROOF },
  { name: 'Kafe Santai ☕', filter: s => s.kind === 'kafe' || s.kind === 'kopi' },
  { name: 'Arena Basket & Pingpong 🏀🏓', filter: s => s.kind === 'hoop' || s.kind === 'ping' },
  { name: 'Piknik & Saung Taman 🧺', filter: s => s.kind === 'picnic' || s.kind === 'bench' },
  { name: 'Sofa Karyawan Lintas Lantai 🛋️', filter: s => s.kind === 'sofa' },
  { name: 'Ayunan & Perosotan 🛝', filter: s => s.kind === 'swing' || s.kind === 'slide' },
];

/**
 * Memicu insting otonom karyawan untuk eksplorasi lintas lantai / outdoor / sosial
 */
export async function triggerLLMInstinct(character) {
  if (!character || character.state === 'chat' || character.talking) return false;

  const currentZone = getLocationLabel(character.pos.x, character.pos.z, character.level);
  const nearbyStaff = staff.filter(s => s !== character && s.level === character.level && s.pos.distanceTo(character.pos) < 6);

  // Construct prompt payload for Autonomous LLM
  const contextPayload = {
    name: character.name,
    role: character.def?.title || 'Staff',
    division: DIVS[character.def?.div]?.name || 'Kantor',
    mood: character.mood,
    currentLevel: character.level,
    currentZone,
    nearbyColleagues: nearbyStaff.map(s => s.name),
    timeOfDay: new Date().getHours() < 12 ? 'Pagi' : new Date().getHours() < 17 ? 'Siang' : 'Sore',
  };

  try {
    let decision = null;

    if (LLM_CONFIG.active && window.fetch) {
      // Call LLM Decision Service (with fallback timeout)
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000);

      try {
        const res = await fetch(LLM_CONFIG.endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(contextPayload),
          signal: controller.signal,
        });
        clearTimeout(timeoutId);
        if (res.ok) decision = await res.json();
      } catch {
        // Fallback to Autonomous Rule Engine if LLM server offline
      }
    }

    if (!decision) {
      decision = generateLocalInstinct(character, contextPayload, nearbyStaff);
    }

    executeInstinctDecision(character, decision);
    return true;
  } catch (err) {
    console.warn('Instinct engine error:', err);
    return false;
  }
}

/**
 * Fallback Local Utility-Based Instinct Engine
 */
function generateLocalInstinct(character, ctx, nearbyStaff) {
  const choices = [
    // 1. Outdoor Pond / Park Exploration
    () => ({
      action: 'explore_outdoor',
      zoneName: 'Kolam Bebek 🦆',
      thought: pick(['Bosan di ruangan, mau liat bebek di kolam ah 🦆', 'Cari udara segar dekat kolam bebek 🌿', 'Refreshing sebentar ke luar']),
      targetFilter: s => s.kind === 'pond' || s.kind === 'bench',
    }),
    // 2. Rooftop Garden
    () => ({
      action: 'explore_roof',
      zoneName: 'Taman Atap 🌿',
      thought: pick(['Naik ke taman atap dulu ah 🌤️', 'Mau lihat pemandangan dari atap gedung 🏙️', 'Nyantai di hammock atap']),
      targetFilter: s => s.level === ROOF,
    }),
    // 3. Visit Cafe / Coffee
    () => ({
      action: 'explore_cafe',
      zoneName: 'Kafe Santai ☕',
      thought: pick(['Ngopi bentar biar nggak ngantuk ☕', 'Beli kopi dulu ke kafe ☕', 'Duduk santai di kafe']),
      targetFilter: s => s.kind === 'kafe' || s.kind === 'kopi',
    }),
    // 4. Cross-Floor Social Visit
    () => ({
      action: 'visit_colleague',
      zoneName: 'Kunjungan Divisi 🏢',
      thought: pick(['Main ke lantai divisi lain ah 🏢', 'Mau nyapa teman di lantai atas 🏢', 'Jalan-jalan antar lantai']),
      targetFilter: s => s.kind === 'sofa' || s.level !== character.level,
    }),
  ];

  if (nearbyStaff.length > 0 && Math.random() < 0.4) {
    const friend = pick(nearbyStaff);
    return {
      action: 'socialize',
      friendName: friend.name,
      thought: `Eh ada ${friend.name}, ngobrol sebentar yuk! 👋`,
      targetFilter: s => s.level === character.level && !s.by,
    };
  }

  return pick(choices)();
}

/**
 * Execute movement & speech based on LLM/Instinct Decision
 */
function executeInstinctDecision(c, decision) {
  const availableSpots = spots.filter(s => !s.by && !s.house && s.level !== 9 && decision.targetFilter(s));
  const chosenSpot = availableSpots.length ? pick(availableSpots) : null;

  if (decision.thought) {
    say(c, decision.thought, 3.2);
  }

  if (chosenSpot) {
    c.state = 'break';
    c.timer = rand(22, 45);
    sendTo(c, chosenSpot, (char, spot) => {
      say(char, pick(['Enak juga di sini ✨', 'Tempatnya nyaman 😊', 'Lanjut nugas abis ini 👍']), 2.8);
    });
  } else {
    // Fallback wander target
    c.state = 'break';
    c.timer = rand(15, 30);
    goBack(c);
  }
}

function getLocationLabel(x, z, level) {
  if (level === ROOF) return 'Taman Atap';
  const dPond = Math.hypot(x - (-30), z - (-6));
  if (dPond < 6) return 'Kolam Bebek';
  if (x >= -9 && x <= 9 && z >= -6 && z <= 6) return `Lantai ${level + 1}`;
  if (z < -18) return 'Taman Terbuka';
  return 'Area Outdoor';
}
