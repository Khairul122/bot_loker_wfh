-- 004: the owner's office in the 3D view: real performance reports and standing instructions

CREATE TABLE IF NOT EXISTS office_reports (
  id TEXT PRIMARY KEY,
  employee TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('daily', 'manual')),
  day TEXT,                       -- local date, only for daily reports
  hours INTEGER NOT NULL,
  score REAL NOT NULL,
  body TEXT NOT NULL,             -- JSON {"metrics": [[icon, label, value]], "lines": [...]}
  rating INTEGER CHECK (rating BETWEEN 1 AND 5),
  note TEXT,
  delivered_at TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_office_reports_daily ON office_reports(employee, day) WHERE kind = 'daily';
CREATE INDEX IF NOT EXISTS idx_office_reports_created ON office_reports(created_at);

CREATE TABLE IF NOT EXISTS office_instructions (
  employee TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
