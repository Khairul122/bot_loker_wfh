// ---------- Employee lessons: learned from owner feedback, stored server-side (Supabase) ----------
import { say } from '../fx/bubbles.js';
import { pick } from '../core/util.js';

const lessons = {};       // empId -> short lesson strings
const loadedAt = {};      // empId -> ms of last fetch
const TTL = 5 * 60 * 1000;

async function refresh(empId) {
  if (!empId || Date.now() - (loadedAt[empId] || 0) < TTL) return;
  loadedAt[empId] = Date.now();
  try {
    const res = await fetch('employee-memory.json?id=' + encodeURIComponent(empId), { cache: 'no-store' });
    if (res.ok) lessons[empId] = (await res.json()).items.map(m => m.content);
  } catch {}
}

/** The server already stored the review as a lesson; just drop the cache so it shows up next time. */
export function recordExperience(empId) {
  delete loadedAt[empId];
  refresh(empId);
}

export function getLearnedSkills(empId) {
  refresh(empId);
  return lessons[empId] || [];
}

/** Colleagues pass real lessons to each other while chatting. */
export function shareSocialKnowledge(staffA, staffB) {
  const [a, b] = [getLearnedSkills(staffA.def?.id), getLearnedSkills(staffB.def?.id)];
  if (a.length && Math.random() < 0.5) {
    say(staffA, `FYI ${staffB.name}: ${pick(a).slice(0, 60)}… 💡`, 3.0);
  } else if (b.length) {
    say(staffB, `Tip dari pengalamanku nih ${staffA.name}: ${pick(b).slice(0, 60)}… 💡`, 3.0);
  }
}
