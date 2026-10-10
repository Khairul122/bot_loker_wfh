-- Supabase Postgres schema. Timestamps are ISO-8601 UTC text (utc_now_iso) so ordering and
-- comparisons stay plain string operations. RLS is on for every table with no policies: only
-- the server-side database role (which bypasses RLS) can read or write.

CREATE OR REPLACE FUNCTION utc_now_iso(shift text DEFAULT NULL) RETURNS text
LANGUAGE sql STABLE AS $$
  SELECT to_char((now() AT TIME ZONE 'utc') + COALESCE(shift::interval, interval '0'),
                 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
$$;

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  source_external_key TEXT NOT NULL,
  canonical_fingerprint TEXT NOT NULL,
  title TEXT NOT NULL,
  company TEXT NOT NULL,
  description TEXT NOT NULL,
  location TEXT,
  salary_min INTEGER,
  salary_max INTEGER,
  currency TEXT,
  apply_url TEXT NOT NULL,
  posted_at TEXT,
  fetched_at TEXT NOT NULL DEFAULT utc_now_iso(),
  relevance_score DOUBLE PRECISION,
  embedding_model TEXT,
  embedding_version TEXT,
  status TEXT NOT NULL DEFAULT 'DISCOVERED',
  filtered_reason TEXT,
  notified_at TEXT,
  UNIQUE (source, external_id),
  UNIQUE (source_external_key),
  UNIQUE (canonical_fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON jobs(posted_at);

CREATE TABLE IF NOT EXISTS applications (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  idempotency_key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'DRAFT_READY',
  cover_letter TEXT NOT NULL,
  cv_summary TEXT NOT NULL,
  method TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT utc_now_iso(),
  approved_at TEXT,
  submitted_at TEXT,
  last_status_check_at TEXT,
  notes TEXT,
  llm_provider TEXT,
  llm_model TEXT,
  UNIQUE (job_id),
  UNIQUE (idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);

CREATE TABLE IF NOT EXISTS submission_attempts (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id),
  attempt_number INTEGER NOT NULL,
  result TEXT NOT NULL,
  error_message TEXT,
  confirmation_url TEXT,
  confirmation_reference TEXT,
  attempted_at TEXT NOT NULL DEFAULT utc_now_iso(),
  UNIQUE (application_id, attempt_number)
);

CREATE TABLE IF NOT EXISTS application_status_history (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id),
  from_status TEXT,
  to_status TEXT NOT NULL,
  changed_by TEXT NOT NULL,
  changed_at TEXT NOT NULL DEFAULT utc_now_iso()
);
CREATE INDEX IF NOT EXISTS idx_status_history_application ON application_status_history(application_id);

CREATE TABLE IF NOT EXISTS filters (
  id TEXT PRIMARY KEY,
  role_keywords TEXT NOT NULL,
  exclusion_keywords TEXT NOT NULL,
  min_relevance_score DOUBLE PRECISION NOT NULL DEFAULT 0.65,
  max_posting_age_days INTEGER NOT NULL DEFAULT 14,
  no_response_after_days INTEGER NOT NULL DEFAULT 21,
  updated_at TEXT NOT NULL DEFAULT utc_now_iso(),
  max_bids INTEGER DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS companies_ats (
  id TEXT PRIMARY KEY,
  company_name TEXT NOT NULL,
  ats_type TEXT NOT NULL,
  ats_slug TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  UNIQUE (ats_type, ats_slug)
);

CREATE TABLE IF NOT EXISTS company_blocklist (
  id TEXT PRIMARY KEY,
  company_name TEXT NOT NULL UNIQUE,
  reason TEXT,
  added_at TEXT NOT NULL DEFAULT utc_now_iso()
);

CREATE TABLE IF NOT EXISTS leads (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  url TEXT NOT NULL,
  budget TEXT,
  posted_at TEXT,
  fetched_at TEXT NOT NULL DEFAULT utc_now_iso(),
  score DOUBLE PRECISION NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'NEW',
  notified_at TEXT,
  proposal TEXT,
  comment TEXT,
  UNIQUE (source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);

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
  created_at TEXT NOT NULL DEFAULT utc_now_iso()
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
  started_at TEXT NOT NULL DEFAULT utc_now_iso(),
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
  confidence DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT utc_now_iso()
);

CREATE TABLE IF NOT EXISTS office_reports (
  id TEXT PRIMARY KEY,
  employee TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('daily', 'manual')),
  day TEXT,                       -- local date, only for daily reports
  hours INTEGER NOT NULL,
  score DOUBLE PRECISION NOT NULL,
  body TEXT NOT NULL,             -- JSON {"metrics": [[icon, label, value]], "lines": [...]}
  rating INTEGER CHECK (rating BETWEEN 1 AND 5),
  note TEXT,
  delivered_at TEXT,
  created_at TEXT NOT NULL DEFAULT utc_now_iso()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_office_reports_daily ON office_reports(employee, day) WHERE kind = 'daily';
CREATE INDEX IF NOT EXISTS idx_office_reports_created ON office_reports(created_at);

CREATE TABLE IF NOT EXISTS office_instructions (
  employee TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT utc_now_iso()
);

CREATE TABLE IF NOT EXISTS office_character_state (
  character_id TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('owner', 'staff')),
  x DOUBLE PRECISION NOT NULL,
  y DOUBLE PRECISION NOT NULL,
  z DOUBLE PRECISION NOT NULL,
  yaw DOUBLE PRECISION NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT utc_now_iso()
);
CREATE INDEX IF NOT EXISTS idx_office_character_state_role ON office_character_state(role);

CREATE TABLE IF NOT EXISTS employee_memory (
  id TEXT PRIMARY KEY,
  employee_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('observation', 'preference', 'correction', 'outcome')),
  content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 2000),
  source TEXT NOT NULL CHECK (length(source) BETWEEN 1 AND 100),
  importance DOUBLE PRECISION NOT NULL CHECK (importance >= 0.0 AND importance <= 1.0),
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_employee_memory_lookup ON employee_memory (employee_id, importance DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS meetings (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
  starts_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('scheduled', 'active', 'completed', 'cancelled')),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meeting_participants (
  meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
  employee_id TEXT NOT NULL,
  PRIMARY KEY (meeting_id, employee_id)
);

CREATE TABLE IF NOT EXISTS meeting_events (
  id TEXT PRIMARY KEY,
  meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
  employee_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN ('join', 'leave', 'note', 'decision', 'action')),
  content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 4000),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meeting_events ON meeting_events(meeting_id, created_at);

ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE submission_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE application_status_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE filters ENABLE ROW LEVEL SECURITY;
ALTER TABLE companies_ats ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_blocklist ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE ats_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE form_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE form_field_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE office_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE office_instructions ENABLE ROW LEVEL SECURITY;
ALTER TABLE office_character_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE employee_memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE meeting_participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE meeting_events ENABLE ROW LEVEL SECURITY;
