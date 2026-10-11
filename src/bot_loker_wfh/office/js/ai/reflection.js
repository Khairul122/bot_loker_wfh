// ---------- Stanford Reflection & Voyager-style Autonomous Learning & Knowledge Share ----------
import { say } from '../fx/bubbles.js';
import { pick } from '../core/util.js';

// Memory Stream per employee
const memoryStream = {};

// Load saved memories from localStorage
try {
  const saved = localStorage.getItem('staff_memories');
  if (saved) Object.assign(memoryStream, JSON.parse(saved));
} catch {}

function saveMemories() {
  try {
    localStorage.setItem('staff_memories', JSON.stringify(memoryStream));
  } catch {}
}

/**
 * Record an experience (Report Review, Project Bid Result, Task Outcome)
 */
export function recordExperience(empId, exp) {
  if (!memoryStream[empId]) {
    memoryStream[empId] = {
      experiences: [],
      insights: [],
      skills: [],
    };
  }

  const mem = memoryStream[empId];
  mem.experiences.push({
    timestamp: Date.now(),
    type: exp.type || 'report_review',
    rating: exp.rating,
    note: exp.note || '',
    score: exp.score || 0,
  });

  // Keep last 30 raw experiences
  if (mem.experiences.length > 30) mem.experiences.shift();

  // Run Stanford Reflection Loop immediately upon new evaluation
  reflectAndInnovate(empId, exp);
  saveMemories();
}

/**
 * Stanford Reflection & Voyager Auto-Skill Synthesizer
 */
function reflectAndInnovate(empId, exp) {
  const mem = memoryStream[empId];
  if (!mem) return;

  const rating = exp.rating;
  const note = exp.note;
  let insight = '';
  let newSkill = '';

  if (rating >= 4) {
    insight = `Strategi kerja berhasil! Pertahankan pendekatan: "${note || 'Kinerja optimal dan tepat waktu'}"`;
    newSkill = `Inovasi: Otomatisasi format laporan & peningkatan standar kualitas`;
  } else if (rating <= 2) {
    insight = `Evaluasi diri: Rating rendah (${rating}/5). Perlu evaluasi instruksi bos: "${note || 'Kurang detail & lambat'}"`;
    newSkill = `Improvisasi: Validasi ganda data & respon instruksi lebih proaktif`;
  } else {
    insight = `Refleksi standar (${rating}/5): Hasil cukup stabil, butuh nilai tambah inovatif`;
    newSkill = `Inovasi: Tambah visualisasi data & ringkasan statistik`;
  }

  // Deduplicate & save high-value insights
  if (!mem.insights.includes(insight)) {
    mem.insights.push(insight);
    if (mem.insights.length > 10) mem.insights.shift();
  }

  if (!mem.skills.includes(newSkill)) {
    mem.skills.push(newSkill);
    if (mem.skills.length > 8) mem.skills.shift();
  }
}

/**
 * Retrieve active learned insights & dynamic skills for an employee
 */
export function getLearnedSkills(empId) {
  const mem = memoryStream[empId];
  if (!mem) return [];
  return [...(mem.insights || []), ...(mem.skills || [])];
}

/**
 * Social Knowledge Share (Karyawan saling berbagi insight saat ngobrol)
 */
export function shareSocialKnowledge(staffA, staffB) {
  const idA = staffA.def?.id;
  const idB = staffB.def?.id;

  const skillsA = getLearnedSkills(idA);
  const skillsB = getLearnedSkills(idB);

  if (skillsA.length > 0 && Math.random() < 0.5) {
    const sharedInsight = pick(skillsA);
    say(staffA, `FYI ${staffB.name}: ${sharedInsight.slice(0, 42)}… 💡`, 3.0);
  } else if (skillsB.length > 0) {
    const sharedInsight = pick(skillsB);
    say(staffB, `Tip dari pengalamanku nih ${staffA.name}: ${sharedInsight.slice(0, 42)}… 💡`, 3.0);
  }
}
