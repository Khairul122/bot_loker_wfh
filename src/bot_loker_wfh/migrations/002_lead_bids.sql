-- Cora's suggested bid terms (hourly rate, weekly limit, duration, milestones) as JSON,
-- shown to the owner next to the proposal and typed into the bid form after approval.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS bid_terms TEXT;
