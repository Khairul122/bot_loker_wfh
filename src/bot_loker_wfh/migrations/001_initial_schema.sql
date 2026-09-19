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
  fetched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  relevance_score REAL,
  embedding_model TEXT,
  embedding_version TEXT,
  status TEXT NOT NULL DEFAULT 'DISCOVERED',
  filtered_reason TEXT,
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
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  approved_at TEXT,
  submitted_at TEXT,
  last_status_check_at TEXT,
  notes TEXT,
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
  attempted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  UNIQUE (application_id, attempt_number)
);

CREATE TABLE IF NOT EXISTS application_status_history (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id),
  from_status TEXT,
  to_status TEXT NOT NULL,
  changed_by TEXT NOT NULL,
  changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_status_history_application
  ON application_status_history(application_id);

CREATE TABLE IF NOT EXISTS filters (
  id TEXT PRIMARY KEY,
  role_keywords TEXT NOT NULL,
  exclusion_keywords TEXT NOT NULL,
  min_relevance_score REAL NOT NULL DEFAULT 0.65,
  max_posting_age_days INTEGER NOT NULL DEFAULT 14,
  no_response_after_days INTEGER NOT NULL DEFAULT 21,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT OR IGNORE INTO filters (
  id,
  role_keywords,
  exclusion_keywords,
  min_relevance_score,
  max_posting_age_days,
  no_response_after_days
) VALUES (
  'default',
  '["laravel", "flutter", "nestjs", "react", "python", "backend", "full stack", "fullstack", "mobile developer", "software engineer", "software developer", "web developer", "programmer"]',
  '["unpaid", "commission only", "equity only", "must relocate"]',
  0.65,
  14,
  21
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
  added_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
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
  fetched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  score REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'NEW',
  notified_at TEXT,
  UNIQUE (source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);

