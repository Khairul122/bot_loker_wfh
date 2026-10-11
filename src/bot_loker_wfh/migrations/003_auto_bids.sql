-- Audit trail for freelance bids: when it was sent, whether the bot sent it on its own,
-- and the reason when the platform refused (an errored lead is never retried automatically).
ALTER TABLE leads ADD COLUMN IF NOT EXISTS bid_submitted_at TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS bid_auto INTEGER NOT NULL DEFAULT 0;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS bid_error TEXT;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS bid_claimed_at TEXT;
