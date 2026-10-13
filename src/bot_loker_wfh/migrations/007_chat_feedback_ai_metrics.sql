ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS employee_id TEXT;

CREATE INDEX IF NOT EXISTS idx_llm_calls_created_employee
  ON llm_calls (created_at DESC, employee_id)
  WHERE employee_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS employee_chat_feedback (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL UNIQUE,
  employee_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('helpful', 'correction', 'lesson')),
  note TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 1000),
  memory_id TEXT REFERENCES employee_memory(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL
);

ALTER TABLE employee_chat_feedback ENABLE ROW LEVEL SECURITY;

UPDATE app_settings
SET value = '0', updated_at = utc_now_iso()
WHERE key = 'auto_bid_enabled' AND value <> '0';
