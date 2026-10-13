-- Daily reports go up the chain: an employee hands theirs to the division manager (handed_at),
-- the manager then brings one division report to the owner (kind 'division', delivered_at).
ALTER TABLE office_reports ADD COLUMN IF NOT EXISTS handed_at TEXT;
ALTER TABLE office_reports DROP CONSTRAINT IF EXISTS office_reports_kind_check;
ALTER TABLE office_reports ADD CONSTRAINT office_reports_kind_check CHECK (kind IN ('daily', 'manual', 'division'));
CREATE UNIQUE INDEX IF NOT EXISTS idx_office_reports_division ON office_reports(employee, day) WHERE kind = 'division';
