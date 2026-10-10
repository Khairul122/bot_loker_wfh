-- 005: durable 3D office character positions

CREATE TABLE IF NOT EXISTS office_character_state (
  character_id TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('owner', 'staff')),
  x REAL NOT NULL,
  y REAL NOT NULL,
  z REAL NOT NULL,
  yaw REAL NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_office_character_state_role
  ON office_character_state(role);
