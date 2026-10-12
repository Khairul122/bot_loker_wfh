const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

const ENERGY_RATE = Object.freeze({
  work: -0.11,
  break: 0.55,
  home: 0.7,
  sleep: 1,
  commute: -0.03,
  back: -0.03,
  chat: -0.025,
  report: -0.04,
  visit: -0.025,
});

export function updateEnergy(energy, state, deltaSeconds) {
  const current = Number.isFinite(energy) ? energy : 80;
  const elapsed = Number.isFinite(deltaSeconds) ? Math.max(0, deltaSeconds) : 0;
  return clamp(current + (ENERGY_RATE[state] ?? -0.03) * elapsed, 0, 100);
}

export function adjustMoodForEnergy(mood, energy, ladder) {
  const current = Math.max(0, Math.min(100, Number(energy) || 0));
  if (mood === 'sedih') return mood;
  const index = ladder.indexOf(mood);
  if (index < 0) return mood;
  if (current < 20) return 'lelah';
  if (current < 42) return ladder[Math.max(0, index - 1)];
  if (current > 92) return ladder[Math.min(ladder.length - 1, index + 1)];
  return mood;
}
