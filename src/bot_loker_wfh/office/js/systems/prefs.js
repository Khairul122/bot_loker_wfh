// ---------- owner preferences (character look, sound, auto mode) kept in Supabase ----------
import { get, post } from '../ui/dom.js';

export async function loadPrefs() {
  const r = await get('office/prefs.json');
  return r.ok ? r.data : {};
}

// awaited variant for forms with an explicit Simpan button
export const savePrefNow = (key, value) => post('office/prefs', { key, value: String(value) });

const timers = {};
// debounced so dragging a colour picker sends one request, not hundreds
export function savePref(key, value, delay = 0) {
  clearTimeout(timers[key]);
  timers[key] = setTimeout(() => { post('office/prefs', { key, value: String(value) }); }, delay);
}
