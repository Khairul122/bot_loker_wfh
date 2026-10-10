// ---------- Settings Panel: Model, Provider, Skills, BrowserMCP, 9Router ----------
import { store } from '../core/store.js';
import { $, el, get, post, toast } from './dom.js';

const SETTINGS_TABS = [
  { id: 'llm', label: '🤖 Model & Provider' },
  { id: 'ninerouter', label: '🔀 9Router' },
  { id: 'browser', label: '🌐 BrowserMCP' },
  { id: 'skills', label: '🛠️ Skills & Tasks' },
  { id: 'form', label: '📝 Form Engine' },
];

let settingsData = null;
let settingsMeta = {}; // raw payload for masked secrets (hint/set)

export async function initSettings() {
  $('bSettings').onclick = () => toggleSettings(true);
  $('settings').onclick = e => { if (e.target === $('settings')) toggleSettings(false); };
  
  await loadSettings();
  renderSettings();
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
    }
  } catch {
    settingsData = {};
    settingsMeta = {};
  }
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
    case 'ninerouter': return renderNineRouterPanel();
    case 'browser': return renderBrowserPanel();
    case 'skills': return renderSkillsPanel();
    case 'form': return renderFormPanel();
    default: return el('div', 'empty', 'Panel tidak ditemukan');
  }
}

function renderLLMPanel() {
  const container = el('div');
  const s = settingsData || {};
  
  container.append(
    el('h4', '', 'Provider LLM Utama'),
    createSelect('llm_provider', 'Provider', [
      { value: 'template', label: '📝 Template (tanpa AI)' },
      { value: 'anthropic', label: '🧠 Anthropic (Claude)' },
      { value: '9router', label: '🔀 9Router (Multi-model)' },
      { value: 'opencode', label: '💻 OpenCode Agent' },
    ], s.llm_provider || 'template', onProviderChange),
    
    el('hr', '', ''),
    
    // Anthropic settings
    createSection([
      el('h4', '', '🧠 Anthropic (Claude)'),
      createInput('anthropic_api_key', 'API Key', 'password', s.anthropic_api_key || '', settingsMeta.anthropic_api_key?.hint ? 'Terset (' + settingsMeta.anthropic_api_key.hint + ') — isi untuk ganti, kosongkan biarkan' : 'Masukkan API key Anthropic'),
      createInput('anthropic_model', 'Model', 'text', s.anthropic_model || 'claude-sonnet-5', 'Contoh: claude-sonnet-5, claude-opus-4'),
    ]),
    
    el('hr', '', ''),
    
    // 9Router settings (shown when 9router selected)
    createSection([
      el('h4', '', '🔀 9Router Configuration'),
      createInput('ninerouter_base_url', 'Base URL', 'text', s.ninerouter_base_url || 'http://localhost:20128/v1', 'Endpoint 9Router'),
      createInput('ninerouter_api_key', 'API Key', 'password', s.ninerouter_api_key || '', 'Key dari dashboard 9Router'),
      createInput('ninerouter_model', 'Model/Combo Utama', 'text', s.ninerouter_model || '', 'Contoh: loker-draft, cc/claude-sonnet-4-5'),
      createTextarea('ninerouter_fallback_models', 'Model Cadangan (comma-separated)', s.ninerouter_fallback_models || '', 'glm/glm-5.1,kr/claude-sonnet-4.5'),
    ], 'section-9router', s.llm_provider === '9router'),
    
    el('hr', '', ''),
    
    // Per-task model routing
    createSection([
      el('h4', '', '🎯 Routing Model per Tugas'),
      createInput('llm_model_draft', 'Cover Letter Draft', 'text', s.llm_model_draft || '', 'Model untuk menulis cover letter'),
      createInput('llm_model_form', 'Form Mapping (JSON)', 'text', s.llm_model_form || '', 'Model stabil untuk output JSON'),
      createInput('llm_model_answer', 'Open Questions', 'text', s.llm_model_answer || '', 'Model untuk jawaban pertanyaan terbuka'),
    ], 'section-task-models', s.llm_provider === '9router'),
    
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
      createButton('🔍 Test Koneksi LLM', 'btn ok', async () => {
        const res = await get('llm/test');
        if (res.ok && res.data.ok !== false) toast('✅ ' + res.data.message);
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

function renderNineRouterPanel() {
  const container = el('div');
  const s = settingsData || {};
  
  container.append(
    el('h4', '', '🔀 Konfigurasi 9Router'),
    createInput('ninerouter_base_url', 'Base URL', 'text', s.ninerouter_base_url || 'http://localhost:20128/v1', 'Endpoint 9Router (default: http://localhost:20128/v1)'),
    createInput('ninerouter_api_key', 'API Key', 'password', s.ninerouter_api_key || '', settingsMeta.ninerouter_api_key?.hint ? 'Terset (' + settingsMeta.ninerouter_api_key.hint + ') — isi untuk ganti, kosongkan biarkan' : 'Dapatkan dari http://localhost:20128/dashboard'),
    
    el('hr', '', ''),
    
    el('h4', '', '📦 Model & Combo'),
    createInput('ninerouter_model', 'Model/Combo Utama', 'text', s.ninerouter_model || '', 'Combo: loker-draft | Single: cc/claude-sonnet-4-5'),
    createTextarea('ninerouter_fallback_models', 'Model Cadangan (pisah koma)', s.ninerouter_fallback_models || '', 'glm/glm-5.1,kr/claude-sonnet-4.5,mini/max'),
    
    el('hr', '', ''),
    
    el('h4', '', '🔗 OpenCode Integration'),
    createInput('opencode_command', 'Perintah OpenCode', 'text', s.opencode_command || 'opencode', 'Path ke binary opencode'),
    createInput('opencode_model', 'Model OpenCode', 'text', s.opencode_model || '9router/ComboOpenCode', 'Format: provider/model'),
    
    el('hr', '', ''),
    
    el('div', 'settings-actions', [
      createButton('🔄 Refresh Model List', 'btn ok', async () => {
        const res = await get('llm/list-models');
        if (res.ok) showModelsModal(res.data);
        else toast('❌ Gagal memuat model');
      }),
      createButton('🧪 Test 9Router Health', 'btn', async () => {
        const res = await get('llm/test');
        if (res.ok && res.data.ok !== false) toast('✅ 9Router sehat: ' + res.data.model);
        else toast('❌ ' + (res.data.error || 'Gagal'));
      }),
    ])
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
    
    el('h4', '', '🎭 Playwright MCP (Alternative)'),
    createInput('playwright_mcp_command', 'Perintah Playwright MCP', 'text', s.playwright_mcp_command || 'npx -y @playwright/mcp@0.0.80 --extension --output-dir data/playwright-mcp', ''),
    
    el('hr', '', ''),
    
    el('h4', '', '🔧 Engine Pengisian Form'),
    createSelect('form_engine_browser', 'Engine Aktif', [
      { value: 'playwright', label: '🎭 Playwright MCP (browser terpisah)' },
      { value: 'browsermcp', label: '🌐 BrowserMCP (Chrome asli Anda)' },
    ], s.form_engine || 'playwright', e => saveSetting('form_engine', e.target.value)),
    
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

function renderSkillsPanel() {
  const container = el('div');
  const s = settingsData || {};
  
  container.append(
    el('h4', '', '🛠️ Skills & Capabilities'),
    el('p', '', 'Kelola skill yang tersedia untuk agent OpenCode. Skill memengaruhi kemampuan bot dalam menulis cover letter, mengisi form, dll.'),
    
    el('hr', '', ''),
    
    el('h4', '', '📋 Skill Tersedia (dari OpenCode)'),
    createBox('skills-list', 'skills-grid', '⏳ Memuat...'),
    
    el('hr', '', ''),
    
    el('div', 'settings-actions', [
      createButton('🔄 Reload Skills dari OpenCode', 'btn ok', async () => {
        const res = await post('skills/reload', {});
        if (res.ok) { toast('✅ Skills dimuat ulang'); loadSkillsList(); }
        else toast('❌ Gagal memuat skill');
      }),
    ])
  );
  
  // Load skills after render
  setTimeout(loadSkillsList, 100);
  
  return container;
}

async function loadSkillsList() {
  const listEl = $('skills-list');
  if (!listEl) return;
  
  try {
    const res = await fetch('skills.json', { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      renderSkillsGrid(listEl, data.skills || []);
    } else {
      listEl.innerHTML = '<div class="empty">Gagal memuat skill</div>';
    }
  } catch {
    listEl.innerHTML = '<div class="empty">Server tidak merespons</div>';
  }
}

function renderSkillsGrid(container, skills) {
  if (!skills.length) {
    container.innerHTML = '<div class="empty">Tidak ada skill terpasang</div>';
    return;
  }
  
  container.replaceChildren(...skills.map(skill => {
    const card = el('div', 'skill-card');
    const enabled = skill.enabled !== false;

    const header = el('div', 'skill-header');
    header.append(el('span', 'skill-name', skill.name ?? ''));

    const label = el('label', 'toggle');
    const checkbox = el('input', '');
    checkbox.type = 'checkbox';
    checkbox.checked = enabled;
    checkbox.dataset.skill = skill.id ?? '';
    checkbox.onchange = async (e) => {
      await post('skills/toggle', { id: skill.id, enabled: e.target.checked });
      toast(e.target.checked ? `✅ ${skill.name} diaktifkan` : `⏸️ ${skill.name} dinonaktifkan`);
    };
    label.append(checkbox, el('span', 'slider'));
    header.append(label);

    const tags = el('div', 'skill-tags');
    tags.append(...(skill.tags || []).map(t => el('span', 'tag', t)));

    card.append(header, el('div', 'skill-desc', skill.description || 'Tidak ada deskripsi'), tags);
    return card;
  }));
}

function renderFormPanel() {
  const container = el('div');
  const s = settingsData || {};
  
  container.append(
    el('h4', '', '📝 Form Engine Settings'),
    createSelect('form_engine', 'Engine Default', [
      { value: 'playwright', label: '🎭 Playwright MCP' },
      { value: 'browsermcp', label: '🌐 BrowserMCP (Chrome asli)' },
    ], s.form_engine || 'playwright'),
    
    el('hr', '', ''),
    
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
      createButton('🧪 Test Form Engine', 'btn ok', async () => {
        const engine = $('#form_engine')?.value || s.form_engine || 'playwright';
        const res = await get('form/test?engine=' + encodeURIComponent(engine));
        if (res.ok && res.data.ok !== false) toast('✅ Engine siap: ' + res.data.engine);
        else toast('❌ ' + (res.data.error || 'Gagal'));
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

// Helper functions for UI components
function createSelect(id, label, options, value, onChange) {
  const wrapper = el('div', 'setting-row');
  const select = el('select', '');
  select.append(...options.map(o => {
    const option = el('option', '', o.label);
    option.value = o.value;
    return option;
  }));
  select.id = id;
  select.value = value;
  // auto-save when onChange not supplied, so form_engine/skill_* persist
  const handler = onChange || ((e) => saveSetting(id, e.target.value));
  select.onchange = handler;
  
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
  input.onchange = () => saveSetting(id, parseFloat(input.value));
  
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

async function saveSetting(key, value) {
  const res = await post('settings', { key, value: String(value) });
  if (res.ok) {
    settingsData[key] = value;
    // Update dependent sections visibility
    if (key === 'llm_provider') {
      const show9router = value === '9router';
      $('#section-9router').style.display = show9router ? 'block' : 'none';
      $('#section-task-models').style.display = show9router ? 'block' : 'none';
    }
    toast('✅ Tersimpan (restart bot untuk berlaku penuh)');
  } else {
    const errorMsg = res.data?.error || (res.status === 403 ? 'Akses ditolak (Origin mismatch)' : res.status ? `HTTP ${res.status}` : 'Server tidak terjangkau');
    toast('❌ Gagal: ' + errorMsg);
    // Reload to revert
    await loadSettings();
    renderSettings();
  }
}

function onProviderChange(e) {
  const provider = e.target.value;
  const section9router = $('#section-9router');
  const sectionTaskModels = $('#section-task-models');
  
  if (section9router) section9router.style.display = provider === '9router' ? 'block' : 'none';
  if (sectionTaskModels) sectionTaskModels.style.display = provider === '9router' ? 'block' : 'none';
  
  saveSetting('llm_provider', provider);
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

function toggleSettings(show) {
  const panel = $('settings');
  panel.classList.toggle('show', show);
  if (show) {
    loadSettings().then(renderSettings);
  }
}