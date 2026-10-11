// ---------- Settings Panel: 9Router, BrowserMCP, Form Engine ----------
import { store } from '../core/store.js';
import { $, el, get, post, toast, closeFlyouts } from './dom.js';

const SETTINGS_TABS = [
  { id: 'llm', label: '🔀 9Router & Model' },
  { id: 'browser', label: '🌐 BrowserMCP' },
  { id: 'form', label: '📝 Form Engine' },
  { id: 'freelance', label: '🤖 Freelance Otomatis' },
];

let settingsData = null;
let settingsMeta = {}; // raw payload for masked secrets (hint/set)
const dirty = new Map(); // key -> pending value (local edit not yet saved)

export async function initSettings() {
  $('bSettings').onclick = () => toggleSettings(!$('settings').classList.contains('show'));
  $('settingsClose').onclick = () => toggleSettings(false);
  $('settings').onclick = e => { if (e.target === $('settings')) toggleSettings(false); };

  await loadSettings();
  renderSettings();
  renderFooter();
}

async function loadSettings() {
  try {
    const res = await fetch('settings.json', { cache: 'no-store' });
    if (res.ok) {
      const raw = await res.json();
      settingsMeta = raw;
      settingsData = {};
      for (const [key, val] of Object.entries(raw)) {
        settingsData[key] = val?.value ?? val;
      }
      dirty.clear();
    }
  } catch {
    settingsData = {};
    settingsMeta = {};
  }
}

function renderFooter() {
  const footer = $('settingsFooter');
  if (!footer) return;

  const count = dirty.size;
  const info = el('span', 'settings-status', count > 0 ? `⚠️ ${count} perubahan belum disimpan` : '✅ Semua tersimpan');
  info.style.fontSize = '12px';
  info.style.fontWeight = '700';
  info.style.color = count > 0 ? 'var(--low)' : 'var(--ink-soft)';

  const saveBtn = el('button', 'save-btn', '💾 Simpan Pengaturan');
  saveBtn.disabled = count === 0;
  saveBtn.onclick = saveAllSettings;

  footer.replaceChildren(info, saveBtn);
}

function markDirty(key, value) {
  dirty.set(key, String(value));
  renderFooter();
}

function renderSettings() {
  const tabsEl = $('settingsTabs');
  const panelsEl = $('settingsPanels');
  
  tabsEl.replaceChildren(...SETTINGS_TABS.map(tab => {
    const btn = el('button', 'chipb' + (tab.id === 'llm' ? ' on' : ''), tab.label);
    btn.dataset.tab = tab.id;
    btn.onclick = () => switchTab(tab.id);
    return btn;
  }));
  
  panelsEl.replaceChildren(...SETTINGS_TABS.map(tab => {
    const panel = el('div', 'settings-panel' + (tab.id === 'llm' ? ' show' : ''));
    panel.id = `settings-${tab.id}`;
    panel.dataset.tab = tab.id;
    panel.append(renderPanelContent(tab.id));
    return panel;
  }));
}

function switchTab(tabId) {
  document.querySelectorAll('#settingsTabs .chipb').forEach(b => {
    b.classList.toggle('on', b.dataset.tab === tabId);
  });
  document.querySelectorAll('.settings-panel').forEach(p => {
    p.classList.toggle('show', p.dataset.tab === tabId);
  });
}

function createSection(children, id = '', visible = true) {
  const section = el('div', 'settings-section');
  if (id) section.id = id;
  section.style.display = visible ? 'block' : 'none';
  section.append(...children);
  return section;
}

function createBox(id, className, text) {
  const box = el('div', className, text);
  box.id = id;
  return box;
}

function createList(items) {
  const list = el('ul', '');
  list.append(...items.map(item => el('li', '', item)));
  return list;
}

function renderPanelContent(tabId) {
  switch (tabId) {
    case 'llm': return renderLLMPanel();
    case 'browser': return renderBrowserPanel();
    case 'form': return renderFormPanel();
    case 'freelance': return renderFreelancePanel();
    default: return el('div', 'empty', 'Panel tidak ditemukan');
  }
}

function renderLLMPanel() {
  const container = el('div');
  const s = settingsData || {};
  
  container.append(
    el('h4', '', '🔀 Konfigurasi 9Router (Provider AI Utama)'),
    createInput('ninerouter_base_url', 'Base URL', 'text', s.ninerouter_base_url || 'http://localhost:20128/v1', 'Endpoint 9Router'),
    createInput('ninerouter_api_key', 'API Key', 'password', s.ninerouter_api_key || '', settingsMeta.ninerouter_api_key?.hint ? 'Terset (' + settingsMeta.ninerouter_api_key.hint + ') — isi untuk ganti, kosongkan biarkan' : 'Key dari dashboard 9Router'),
    createInput('ninerouter_model', 'Model/Combo Utama', 'text', s.ninerouter_model || 'LokerHouse', 'Contoh: LokerHouse, loker-draft, cc/claude-sonnet-4-5'),
    createTextarea('ninerouter_fallback_models', 'Model Cadangan (comma-separated)', s.ninerouter_fallback_models || '', 'glm/glm-5.1,kr/claude-sonnet-4.5'),
    
    el('hr', '', ''),
    
    // Per-task model routing
    createSection([
      el('h4', '', '🎯 Routing Model per Tugas'),
      createInput('llm_model_draft', 'Cover Letter Draft', 'text', s.llm_model_draft || '', 'Model untuk menulis cover letter'),
      createInput('llm_model_form', 'Form Mapping (JSON)', 'text', s.llm_model_form || '', 'Model stabil untuk output JSON'),
      createInput('llm_model_answer', 'Open Questions', 'text', s.llm_model_answer || '', 'Model untuk jawaban pertanyaan terbuka'),
    ]),
    
    el('hr', '', ''),
    
    // Global LLM params
    createSection([
      el('h4', '', '⚙️ Parameter Global'),
      createNumberInput('llm_timeout_seconds', 'Timeout per Request (detik)', s.llm_timeout_seconds || 60, 5, 300),
      createNumberInput('llm_task_budget_seconds', 'Budget Total per Tugas (detik)', s.llm_task_budget_seconds || 90, 10, 600),
      createNumberInput('llm_temperature_draft', 'Temperature Draft', s.llm_temperature_draft || 0.4, 0, 2, 0.1),
    ]),
    
    el('hr', '', ''),
    
    // Actions
    el('div', 'settings-actions', [
      createButton('🔍 Test Koneksi 9Router', 'btn ok', async () => {
        const res = await get('llm/test');
        if (res.ok && res.data.ok !== false) toast('✅ ' + (res.data.message || '9Router sehat: ' + res.data.model));
        else toast('❌ ' + (res.data.error || 'Gagal'));
      }),
      createButton('📋 Lihat Model 9Router', 'btn', async () => {
        const res = await get('llm/list-models');
        if (res.ok) showModelsModal(res.data);
        else toast('❌ Gagal memuat model');
      }),
    ])
  );
  
  return container;
}

function renderFreelancePanel() {
  const container = el('div');
  const s = settingsData || {};
  container.append(
    el('h4', '', '🤖 Bid Freelancer otomatis (tanpa persetujuan)'),
    el('p', '', 'Kalau aktif, setiap putaran kerja: Cora menulis draf untuk proyek Freelancer baru, lalu bid yang lolos aturan di bawah dikirim lewat API resmi. Hasilnya dikabari lewat Telegram. Karyawan dan server harus tetap menyala.'),
    createSelect('auto_bid_enabled', 'Auto-bid', [
      { value: '0', label: '⏸️ Mati (kamu setujui satu per satu)' },
      { value: '1', label: '🤖 Aktif (bid dikirim otomatis)' },
    ], String(s.auto_bid_enabled || '0')),
    createNumberInput('auto_bid_max_per_day', 'Maks bid per 24 jam', s.auto_bid_max_per_day || 5, 1, 50),
    createNumberInput('auto_bid_min_score', 'Skor relevansi minimum (0-1)', s.auto_bid_min_score || 0.7, 0, 1, 0.05),
    createNumberInput('auto_bid_max_competitors', 'Lewati proyek dengan bid lebih dari', s.auto_bid_max_competitors || 40, 1, 500),
    createNumberInput('auto_bid_max_age_hours', 'Hanya proyek yang diposting dalam (jam)', s.auto_bid_max_age_hours || 24, 1, 720),
    el('hr', '', ''),
    createList([
      '✅ Hanya Freelancer.com (API resmi); Projects.co.id tetap lewat persetujuanmu',
      '💰 Harga = rata-rata bid platform (tidak di bawahnya), tenggang waktu dari Cora',
      '🛑 Satu penolakan menghentikan putaran itu; token/kuota bermasalah mematikan auto-bid',
      '🔁 Proyek yang ditolak tidak dicoba ulang otomatis',
    ]),
  );
  return container;
}

function renderBrowserPanel() {
  const container = el('div');
  const s = settingsData || {};
  
  container.append(
    el('h4', '', '🌐 BrowserMCP Configuration'),
    createInput('browser_mcp_command', 'Perintah BrowserMCP', 'text', s.browser_mcp_command || 'npx -y @browsermcp/mcp@0.1.3', 'Versi terkunci untuk stabilitas snapshot'),
    
    
    el('hr', '', ''),
    
    el('h4', '', '⏱️ Timeout & Limits'),
    createNumberInput('form_timeout_seconds', 'Timeout Sesi (detik)', s.form_timeout_seconds || 300, 30, 1800),
    createNumberInput('form_connect_timeout_seconds', 'Timeout Connect (detik)', s.form_connect_timeout_seconds || 20, 5, 120),
    createNumberInput('form_max_tool_calls', 'Max Tool Calls per Sesi', s.form_max_tool_calls || 80, 10, 300),
    createNumberInput('form_max_actions', 'Max Actions per Halaman', s.form_max_actions || 60, 10, 200),
    
    el('hr', '', ''),
    
    el('div', 'settings-actions', [
      createButton('🔍 Test BrowserMCP', 'btn ok', async () => {
        const res = await get('browser/test');
        if (res.ok && res.data.ok !== false) toast('✅ BrowserMCP terhubung');
        else toast('❌ ' + (res.data.error || 'Gagal - pastikan ekstensi Connect'));
      }),
      createButton('📋 List ATS Registry', 'btn', async () => {
        const res = await get('ats/list');
        if (res.ok) showATSModal(res.data);
        else toast('❌ Gagal memuat ATS');
      }),
    ])
  );
  
  return container;
}

function renderFormPanel() {
  const container = el('div');
  const s = settingsData || {};
  
  container.append(
    el('h4', '', '📝 Pengisian Form (BrowserMCP)'),
    
    el('h4', '', '🎯 AI Answers Configuration'),
    createSelect('form_ai_answers', 'Jawaban AI untuk Pertanyaan Terbuka', [
      { value: 'review', label: '📝 Review - AI jawab, user cek sebelum submit' },
      { value: 'off', label: '⏸️ Off - Hanya isi field identitas/link/cover letter' },
    ], s.form_ai_answers || 'review'),
    
    createNumberInput('form_min_confidence', 'Min Confidence AI', s.form_min_confidence || 0.7, 0.1, 1.0, 0.05),
    
    el('hr', '', ''),
    
    el('h4', '', '🛡️ Policy Guard'),
    el('p', '', 'Aturan keamanan yang tidak bisa dilanggar AI:'),
    createList([
      '❌ Tidak pernah klik Submit/Apply/Kirim',
      '❌ Tidak isi field sensitif (gender, ras, veteran, disabilitas)',
      '❌ Tidak isi field legal (persetujuan, privacy, terms)',
      '❌ Tidak kirim data pribadi (email, phone, nama) ke AI',
      '❌ Placeholder wajib untuk field identitas',
      '❌ Opsi dropdown harus cocok persis',
    ]),
    
    el('hr', '', ''),
    
    el('h4', '', '📂 Data Files'),
    createInput('applicant_path', 'Applicant Data', 'text', s.applicant_path || 'data/applicant.json', 'Path ke data/applicant.json'),
    createInput('answers_path', 'Answers Database', 'text', s.answers_path || 'data/answers.json', 'Path ke data/answers.json v2'),
    
    el('hr', '', ''),
    
    el('div', 'settings-actions', [
      createButton('📋 List ATS Registry', 'btn', async () => {
        const res = await get('ats/list');
        if (res.ok) showATSModal(res.data);
        else toast('❌ Gagal memuat ATS');
      }),
    ])
  );
  
  return container;
}

// Helper functions for UI components
function createSelect(id, label, options, value, onChange, key = id) {
  const wrapper = el('div', 'setting-row');
  const select = el('select', '');
  select.append(...options.map(o => {
    const option = el('option', '', o.label);
    option.value = o.value;
    return option;
  }));
  select.id = id;
  select.value = value;
  
  select.onchange = (e) => {
    markDirty(key, e.target.value);
    if (onChange) onChange(e);
    else saveSetting(key, e.target.value);
  };
  
  wrapper.append(
    el('label', '', label),
    select
  );
  return wrapper;
}

function createInput(id, label, type, value, placeholder) {
  const wrapper = el('div', 'setting-row');
  const input = el('input', '');
  input.id = id;
  input.type = type;
  input.value = value;
  input.placeholder = placeholder;
  
  input.oninput = () => markDirty(id, input.value);
  input.onchange = () => saveSetting(id, input.value);
  
  wrapper.append(
    el('label', '', label),
    input
  );
  return wrapper;
}

function createTextarea(id, label, value, placeholder) {
  const wrapper = el('div', 'setting-row');
  const textarea = el('textarea', '');
  textarea.id = id;
  textarea.value = value;
  textarea.placeholder = placeholder;
  textarea.rows = 3;
  
  textarea.oninput = () => markDirty(id, textarea.value);
  textarea.onchange = () => saveSetting(id, textarea.value);
  
  wrapper.append(
    el('label', '', label),
    textarea
  );
  return wrapper;
}

function createNumberInput(id, label, value, min, max, step = 1) {
  const wrapper = el('div', 'setting-row');
  const input = el('input', '');
  input.id = id;
  input.type = 'number';
  input.value = value;
  input.min = min;
  input.max = max;
  input.step = step;
  
  input.oninput = () => markDirty(id, input.value);
  input.onchange = () => {
    const number = parseFloat(input.value);
    if (Number.isNaN(number)) { toast('❌ Isi angka yang valid'); loadSettings().then(renderSettings).then(renderFooter); return; }
    saveSetting(id, number);
  };
  
  wrapper.append(
    el('label', '', label),
    input
  );
  return wrapper;
}

function createButton(text, className, onClick) {
  const btn = el('button', className, text);
  btn.onclick = onClick;
  return btn;
}

async function saveAllSettings() {
  if (!dirty.size) { toast('Tidak ada perubahan untuk disimpan'); return; }
  toast('⏳ Menyimpan ke Supabase...');
  // one request, all-or-nothing: only what was actually edited
  const res = await post('settings', { values: Object.fromEntries(dirty) });
  if (res.ok) {
    dirty.clear();
    await loadSettings();
    renderFooter();
    toast('✅ Pengaturan tersimpan di Supabase');
  } else {
    const why = res.data?.error || (res.status ? `HTTP ${res.status}` : 'Server tidak terjangkau');
    toast('❌ Gagal menyimpan' + (res.data?.key ? ` (${res.data.key})` : '') + ': ' + why);
  }
}

async function saveSetting(key, value) {
  const res = await post('settings', { key, value: String(value) });
  if (res.ok) {
    settingsData[key] = value;
    dirty.delete(key);
    renderFooter();
    toast('✅ Tersimpan (restart bot untuk berlaku penuh)');
  } else {
    const errorMsg = res.data?.error || (res.status === 403 ? 'Akses ditolak (Origin mismatch)' : res.status ? `HTTP ${res.status}` : 'Server tidak terjangkau');
    toast('❌ Gagal: ' + errorMsg);
    // Reload to revert
    await loadSettings();
    renderSettings();
    renderFooter();
  }
}

function openModal(title, buildBody) {
  const trigger = document.activeElement;
  const modal = el('div', 'modal-overlay');
  const content = el('div', 'modal-content');
  content.setAttribute('role', 'dialog');
  content.setAttribute('aria-modal', 'true');
  content.setAttribute('aria-label', title);

  const header = el('div', 'modal-header');
  header.append(el('h3', '', title));
  const close = el('button', 'modal-close', '✕');
  close.setAttribute('aria-label', 'Tutup');
  close.type = 'button';
  header.append(close);

  const body = el('div', 'modal-body');
  buildBody(body);

  content.append(header, body);
  modal.append(content);
  document.body.append(modal);

  const dismiss = () => {
    modal.remove();
    document.removeEventListener('keydown', onKey);
    if (trigger && typeof trigger.focus === 'function') trigger.focus();
  };
  const onKey = e => { if (e.key === 'Escape') dismiss(); };
  document.addEventListener('keydown', onKey);
  close.onclick = dismiss;
  modal.onclick = e => { if (e.target === modal) dismiss(); };
  close.focus();
}

function appendList(parent, heading, items, format) {
  if (!items?.length) return;
  parent.append(el('h4', '', heading));
  const list = el('ul', '');
  list.append(...items.map(item => el('li', '', format(item))));
  parent.append(list);
}

function showModelsModal(data) {
  openModal('📋 Model 9Router Tersedia', body => {
    appendList(body, '🔀 Combo Models', data.combo, m => String(m));
    appendList(body, '👁️ Vision Models', data.vision, m => String(m));
    appendList(body, '📦 Semua Model', data.all, m => `${m.id} (${m.owned_by || 'unknown'})`);
    if (data.error) body.append(el('p', 'error', 'Error: ' + data.error));
  });
}

function showATSModal(data) {
  openModal('📋 ATS Registry', body => {
    const table = el('table', 'ats-table');
    const head = el('tr', '');
    ['ATS', 'Host', 'Mode', 'Open Button', 'Status'].forEach(h => head.append(el('th', '', h)));
    const thead = el('thead', '');
    thead.append(head);
    const tbody = el('tbody', '');
    const rows = data.ats || [];
    if (!rows.length) {
      const cell = el('td', '', 'Tidak ada ATS terdaftar');
      cell.colSpan = 5;
      const tr = el('tr', '');
      tr.append(cell);
      tbody.append(tr);
    } else {
      rows.forEach(a => {
        const tr = el('tr', '');
        tr.append(el('td', '', a.ats_name ?? ''));
        tr.append(el('td', '', a.host ?? ''));
        const mode = el('td', '');
        mode.append(el('span', 'tag ' + (a.mode === 'auto_fill' ? 'good' : 'mid'), a.mode ?? ''));
        tr.append(mode);
        tr.append(el('td', '', a.open_button_label || '-'));
        tr.append(el('td', '', a.active ? '🟢 Active' : '🔴 Inactive'));
        tbody.append(tr);
      });
    }
    table.append(thead, tbody);
    body.append(table);
  });
}

export function toggleSettings(show = !$('settings').classList.contains('show')) {
  const panel = $('settings');
  panel.classList.toggle('show', show);
  panel.setAttribute('aria-hidden', String(!show));
  if (show) {
    closeFlyouts('settings');
    loadSettings().then(renderSettings);
  }
}