CREATE TABLE IF NOT EXISTS employee_conversations (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  employee_id TEXT NOT NULL,
  speaker TEXT NOT NULL CHECK (speaker IN ('owner', 'employee')),
  channel TEXT NOT NULL CHECK (channel IN ('web_chat')),
  content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 4000),
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_employee_conversations_recent
  ON employee_conversations (created_at DESC, employee_id);

ALTER TABLE employee_conversations ENABLE ROW LEVEL SECURITY;
