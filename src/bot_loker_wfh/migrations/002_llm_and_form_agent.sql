ALTER TABLE applications ADD COLUMN llm_provider TEXT;
ALTER TABLE applications ADD COLUMN llm_model TEXT;

CREATE TABLE IF NOT EXISTS llm_calls (
  id TEXT PRIMARY KEY,
  run_id TEXT,
  task TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  attempt INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL,
  error_code TEXT,
  latency_ms INTEGER,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  application_id TEXT REFERENCES applications(id),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_created ON llm_calls(created_at);

CREATE TABLE IF NOT EXISTS ats_registry (
  id TEXT PRIMARY KEY,
  ats_name TEXT NOT NULL,
  host TEXT NOT NULL UNIQUE,
  mode TEXT NOT NULL CHECK (mode IN ('auto_fill', 'assist')),
  open_button_label TEXT,
  verified_at TEXT,
  active INTEGER NOT NULL DEFAULT 1
);

INSERT OR IGNORE INTO ats_registry (id, ats_name, host, mode, open_button_label) VALUES
  ('gh-1', 'Greenhouse', 'job-boards.greenhouse.io', 'auto_fill', NULL),
  ('gh-2', 'Greenhouse', 'boards.greenhouse.io', 'auto_fill', NULL),
  ('lv-1', 'Lever', 'jobs.lever.co', 'auto_fill', 'Apply for this job'),
  ('lv-2', 'Lever', 'jobs.eu.lever.co', 'auto_fill', 'Apply for this job'),
  ('ab-1', 'Ashby', 'jobs.ashbyhq.com', 'assist', 'Apply'),
  ('wk-1', 'Workable', 'apply.workable.com', 'assist', 'Apply for this job'),
  ('sr-1', 'SmartRecruiters', 'jobs.smartrecruiters.com', 'assist', 'I''m interested'),
  ('kb-1', 'Kalibrr', 'www.kalibrr.com', 'assist', 'Apply');

CREATE TABLE IF NOT EXISTS form_sessions (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id),
  engine TEXT NOT NULL,
  host TEXT NOT NULL,
  mode TEXT NOT NULL,
  page_number INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL,
  filled_count INTEGER NOT NULL DEFAULT 0,
  ai_answer_count INTEGER NOT NULL DEFAULT 0,
  manual_count INTEGER NOT NULL DEFAULT 0,
  skipped_protected_count INTEGER NOT NULL DEFAULT 0,
  captcha INTEGER NOT NULL DEFAULT 0,
  tool_calls INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  user_feedback TEXT,
  started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_form_sessions_application ON form_sessions(application_id);

CREATE TABLE IF NOT EXISTS form_field_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES form_sessions(id),
  label TEXT NOT NULL,
  role TEXT NOT NULL,
  field_class TEXT NOT NULL,
  action TEXT NOT NULL,
  source TEXT,
  reason TEXT,
  confidence REAL
);
