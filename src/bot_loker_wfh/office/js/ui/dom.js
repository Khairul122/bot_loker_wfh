export const $ = id => document.getElementById(id);
export const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

let toastT;
export function toast(t) { const box = $('toast'); box.textContent = t; box.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => box.classList.remove('show'), 3200); }

export async function get(path) {
  try {
    const r = await fetch(path, { cache: 'no-store' });
    return { ok: r.ok, status: r.status, data: await r.json().catch(() => ({})) };
  } catch { return { ok: false, status: 0, data: {} }; }
}

export async function post(path, body) {
  try {
    const r = await fetch(path, { method: 'POST', headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
    return { ok: r.ok, status: r.status, data: await r.json().catch(() => ({})) };
  } catch { return { ok: false, status: 0, data: {} }; }
}

export function ago(iso) {
  const t = Date.parse(iso || ''); if (!t) return '';
  const m = Math.round((Date.now() - t) / 60000);
  return m < 60 ? `${Math.max(1, m)} menit lalu` : m < 1440 ? `${Math.round(m / 60)} jam lalu` : `${Math.round(m / 1440)} hari lalu`;
}

export const scoreColor = s => s >= 0.6 ? 'var(--good)' : s >= 0.4 ? 'var(--mid)' : s >= 0.2 ? 'var(--low)' : 'var(--idle)';
export const starsHtml = s => { const n = Math.round(s * 5); return '★'.repeat(n) + `<span class="off">${'★'.repeat(5 - n)}</span>`; };
export const hex = n => '#' + n.toString(16).padStart(6, '0');
export const faceStyle = c => `background:${hex(c.look.shirt)}`;
export const OFFLINE = 'Jalankan: python -m bot_loker_wfh office';
