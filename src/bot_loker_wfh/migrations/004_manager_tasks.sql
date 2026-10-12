-- Internal division work only. This table has no integration with job or bid submission.
CREATE TABLE IF NOT EXISTS office_manager_tasks (
  id TEXT PRIMARY KEY,
  division TEXT NOT NULL,
  manager TEXT NOT NULL,
  assignee TEXT NOT NULL,
  title TEXT NOT NULL CHECK (length(title) BETWEEN 3 AND 160),
  priority TEXT NOT NULL CHECK (priority IN ('low', 'normal', 'high')) DEFAULT 'normal',
  status TEXT NOT NULL CHECK (status IN ('assigned', 'in_progress', 'reviewed')) DEFAULT 'assigned',
  review_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT utc_now_iso(),
  updated_at TEXT NOT NULL DEFAULT utc_now_iso()
);
CREATE INDEX IF NOT EXISTS idx_office_manager_tasks_division_updated
  ON office_manager_tasks (division, updated_at DESC);
ALTER TABLE office_manager_tasks ENABLE ROW LEVEL SECURITY;
