// ---------- Settings Panel: Model, Provider, Skills, BrowserMCP, 9Router ----------
import { store } from '../core/store.js';
import { $, el, post, toast } from './dom.js';

const SETTINGS_TABS = [
  { id: 'llm', label: '🤖 Model & Provider' },
  { id: 'ninerouter', label: '🔀 9Router' },
  { id: 'browser', label: '🌐 BrowserMCP' },
  { id: 'skills', label: '🛠️ Skills & Tasks' },
  { id: 'form', label: '📝 Form Engine' },
];

let settingsData = null;

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
      // Extract values from {key: {value: ...}} format
      settingsData = {};
      for (const [key, val] of Object.entries(raw)) {
        settingsData[key] = val?.value ?? val;
      }
    }
  } catch {
    settingsData = {};
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
    el('div', 'settings-section', [
      el('h4', '', '🧠 Anthropic (Claude)'),
      createInput('anthropic_api_key', 'API Key', 'password', s.anthropic_api_key || '', 'Masukkan API key Anthropic'),
      createInput('anthropic_model', 'Model', 'text', s.anthropic_model || 'claude-sonnet-5', 'Contoh: claude-sonnet-5, claude-opus-4'),
    ].map(e => typeof e === 'string' ? el('div', '', e) : e).filter(Boolean)),
    
    el('hr', '', ''),
    
    // 9Router settings (shown when 9router selected)
    el('div', 'settings-section', { id: 'section-9router', style: 'display:' + ((s.llm_provider === '9router') ? 'block' : 'none') }, [
      el('h4', '', '🔀 9Router Configuration'),
      createInput('ninerouter_base_url', 'Base URL', 'text', s.ninerouter_base_url || 'http://localhost:20128/v1', 'Endpoint 9Router'),
      createInput('ninerouter_api_key', 'API Key', 'password', s.ninerouter_api_key || '', 'Key dari dashboard 9Router'),
      createInput('ninerouter_model', 'Model/Combo Utama', 'text', s.ninerouter_model || '', 'Contoh: loker-draft, cc/claude-sonnet-4-5'),
      createTextarea('ninerouter_fallback_models', 'Model Cadangan (comma-separated)', s.ninerouter_fallback_models || '', 'glm/glm-5.1,kr/claude-sonnet-4.5'),
    ].map(e => typeof e === 'string' ? el('div', '', e) : e).filter(Boolean)),
    
    el('hr', '', ''),
    
    // Per-task model routing
    el('div', 'settings-section', { id: 'section-task-models', style: 'display:' + ((s.llm_provider === '9router') ? 'block' : 'none') }, [
      el('h4', '', '🎯 Routing Model per Tugas'),
      createInput('llm_model_draft', 'Cover Letter Draft', 'text', s.llm_model_draft || '', 'Model untuk menulis cover letter'),
      createInput('llm_model_form', 'Form Mapping (JSON)', 'text', s.llm_model_form || '', 'Model stabil untuk output JSON'),
      createInput('llm_model_answer', 'Open Questions', 'text', s.llm_model_answer || '', 'Model untuk jawaban pertanyaan terbuka'),
    ].map(e => typeof e === 'string' ? el('div', '', e) : e).filter(Boolean)),
    
    el('hr', '', ''),
    
    // Global LLM params
    el('div', 'settings-section', [
      el('h4', '', '⚙️ Parameter Global'),
      createNumberInput('llm_timeout_seconds', 'Timeout per Request (detik)', s.llm_timeout_seconds || 60, 5, 300),
      createNumberInput('llm_task_budget_seconds', 'Budget Total per Tugas (detik)', s.llm_task_budget_seconds || 90, 10, 600),
      createNumberInput('llm_temperature_draft', 'Temperature Draft', s.llm_temperature_draft || 0.4, 0, 2, 0.1),
    ].map(e => typeof e === 'string' ? el('div', '', e) : e).filter(Boolean)),
    
    el('hr', '', ''),
    
    // Actions
    el('div', 'settings-actions', [
      createButton('🔍 Test Koneksi LLM', 'btn ok', async () => {
        const res = await post('llm/test', {});
        if (res.ok) toast('✅ ' + res.data.message);
        else toast('❌ ' + (res.data.error || 'Gagal'));
      }),
      createButton('📋 Lihat Model 9Router', 'btn', async () => {
        const res = await post('llm/list-models', {});
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
    createInput('ninerouter_api_key', 'API Key', 'password', s.ninerouter_api_key || '', 'Dapatkan dari http://localhost:20128/dashboard'),
    
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
        const res = await post('llm/list-models', {});
        if (res.ok) showModelsModal(res.data);
        else toast('❌ Gagal memuat model');
      }),
      createButton('🧪 Test 9Router Health', 'btn', async () => {
        const res = await post('llm/test', { provider: '9router' });
        if (res.ok) toast('✅ 9Router sehat: ' + res.data.model);
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
    createSelect('form_engine', 'Engine Aktif', [
      { value: 'playwright', label: '🎭 Playwright MCP (browser terpisah)' },
      { value: 'browsermcp', label: '🌐 BrowserMCP (Chrome asli Anda)' },
    ], s.form_engine || 'playwright'),
    
    el('hr', '', ''),
    
    el('h4', '', '⏱️ Timeout & Limits'),
    createNumberInput('form_timeout_seconds', 'Timeout Sesi (detik)', s.form_timeout_seconds || 300, 30, 1800),
    createNumberInput('form_connect_timeout_seconds', 'Timeout Connect (detik)', s.form_connect_timeout_seconds || 20, 5, 120),
    createNumberInput('form_max_tool_calls', 'Max Tool Calls per Sesi', s.form_max_tool_calls || 80, 10, 300),
    createNumberInput('form_max_actions', 'Max Actions per Halaman', s.form_max_actions || 60, 10, 200),
    
    el('hr', '', ''),
    
    el('div', 'settings-actions', [
      createButton('🔍 Test BrowserMCP', 'btn ok', async () => {
        const res = await post('browser/test', {});
        if (res.ok) toast('✅ BrowserMCP terhubung');
        else toast('❌ ' + (res.data.error || 'Gagal - pastikan ekstensi Connect'));
      }),
      createButton('📋 List ATS Registry', 'btn', async () => {
        const res = await post('ats/list', {});
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
    el('div', { id: 'skills-list', class: 'skills-grid' }, '⏳ Memuat...'),
    
    el('hr', '', ''),
    
    el('h4', '', '🎯 Task Routing'),
    el('p', '', 'Tentukan skill/agent mana yang handle tugas tertentu:'),
    createSelect('skill_draft', 'Cover Letter Draft', [
      { value: 'default', label: 'Default (prompt_builder)' },
      { value: 'cover_letter', label: 'Skill cover-letter-specialist' },
      { value: 'opencode', label: 'OpenCode Agent' },
    ], s.skill_draft || 'default'),
    
    createSelect('skill_form', 'Form Mapping', [
      { value: 'default', label: 'Default (FormAgent)' },
      { value: 'form_filler', label: 'Skill form-filler-expert' },
      { value: 'opencode', label: 'OpenCode Agent' },
    ], s.skill_form || 'default'),
    
    createSelect('skill_answer', 'Open Questions', [
      { value: 'default', label: 'Default (LLM answer)' },
      { value: 'qa_expert', label: 'Skill qa-specialist' },
      { value: 'opencode', label: 'OpenCode Agent' },
    ], s.skill_answer || 'default'),
    
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
    card.innerHTML = `
      <div class="skill-header">
        <span class="skill-name">${skill.name}</span>
        <label class="toggle">
          <input type="checkbox" ${enabled ? 'checked' : ''} data-skill="${skill.id}">
          <span class="slider"></span>
        </label>
      </div>
      <div class="skill-desc">${skill.description || 'Tidak ada deskripsi'}</div>
      <div class="skill-tags">${(skill.tags || []).map(t => `<span class="tag">${t}</span>`).join('')}</div>
    `;
    card.querySelector('input').onchange = async (e) => {
      await post('skills/toggle', { id: skill.id, enabled: e.target.checked });
      toast(e.target.checked ? `✅ ${skill.name} diaktifkan` : `⏸️ ${skill.name} dinonaktifkan`);
    };
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
    el('ul', '', [
      '❌ Tidak pernah klik Submit/Apply/Kirim',
      '❌ Tidak isi field sensitif (gender, ras, veteran, disabilitas)',
      '❌ Tidak isi field legal (persetujuan, privacy, terms)',
      '❌ Tidak kirim data pribadi (email, phone, nama) ke AI',
      '❌ Placeholder wajib untuk field identitas',
      '❌ Opsi dropdown harus cocok persis',
    ].map(item => `<li>${item}</li>`).join('')),
    
    el('hr', '', ''),
    
    el('h4', '', '📂 Data Files'),
    createInput('applicant_path', 'Applicant Data', 'text', s.applicant_path || 'data/applicant.json', 'Path ke data/applicant.json'),
    createInput('answers_path', 'Answers Database', 'text', s.answers_path || 'data/answers.json', 'Path ke data/answers.json v2'),
    
    el('hr', '', ''),
    
    el('div', 'settings-actions', [
      createButton('🧪 Test Form Engine', 'btn ok', async () => {
        const res = await post('form/test', { engine: s.form_engine });
        if (res.ok) toast('✅ Engine siap: ' + res.data.engine);
        else toast('❌ ' + (res.data.error || 'Gagal'));
      }),
      createButton('📋 List ATS Registry', 'btn', async () => {
        const res = await post('ats/list', {});
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
  const select = el('select', '', options.map(o => 
    `<option value="${o.value}" ${o.value === value ? 'selected' : ''}>${o.label}</option>`
  ).join(''));
  select.id = id;
  select.value = value;
  if (onChange) select.onchange = onChange;
  
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
    toast('❌ Gagal: ' + (res.data.error || 'Unknown'));
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

function showModelsModal(data) {
  // Create modal for model list
  const modal = el('div', 'modal-overlay');
  const content = el('div', 'modal-content');
  
  content.innerHTML = `
    <div class="modal-header">
      <h3>📋 Model 9Router Tersedia</h3>
      <button class="modal-close">✕</button>
    </div>
    <div class="modal-body">
      ${data.combo?.length ? `
        <h4>🔀 Combo Models</h4>
        <ul>${data.combo.map(m => `<li>${m}</li>`).join('')}</ul>
      ` : ''}
      ${data.vision?.length ? `
        <h4>👁️ Vision Models</h4>
        <ul>${data.vision.map(m => `<li>${m}</li>`).join('')}</ul>
      ` : ''}
      ${data.all?.length ? `
        <h4>📦 Semua Model</h4>
        <ul>${data.all.map(m => `<li>${m.id} (${m.owned_by || 'unknown'})</li>`).join('')}</ul>
      ` : ''}
      ${data.error ? `<p class="error">Error: ${data.error}</p>` : ''}
    </div>
  `;
  
  modal.append(content);
  document.body.append(modal);
  
  content.querySelector('.modal-close').onclick = () => modal.remove();
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
}

function showATSModal(data) {
  const modal = el('div', 'modal-overlay');
  const content = el('div', 'modal-content');
  
  content.innerHTML = `
    <div class="modal-header">
      <h3>📋 ATS Registry</h3>
      <button class="modal-close">✕</button>
    </div>
    <div class="modal-body">
      <table class="ats-table">
        <thead><tr><th>ATS</th><th>Host</th><th>Mode</th><th>Open Button</th><th>Status</th></tr></thead>
        <tbody>
          ${data.ats?.map(a => `
            <tr>
              <td>${a.ats_name}</td>
              <td>${a.host}</td>
              <td><span class="tag ${a.mode === 'auto_fill' ? 'good' : 'mid'}">${a.mode}</span></td>
              <td>${a.open_button_label || '-'}</td>
              <td>${a.active ? '🟢 Active' : '🔴 Inactive'}</td>
            </tr>
          `).join('') || '<tr><td colspan="5">Tidak ada ATS terdaftar</td></tr>'}
        </tbody>
      </table>
    </div>
  `;
  
  modal.append(content);
  document.body.append(modal);
  
  content.querySelector('.modal-close').onclick = () => modal.remove();
  modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
}

function toggleSettings(show) {
  const panel = $('settings');
  panel.classList.toggle('show', show);
  if (show) {
    loadSettings().then(renderSettings);
  }
}