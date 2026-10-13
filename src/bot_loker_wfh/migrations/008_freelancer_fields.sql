-- Track the Freelancer field used to discover each lead. Historical leads were
-- all found through the original software searches, so the default is accurate.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS freelancer_field TEXT NOT NULL DEFAULT 'software';
CREATE INDEX IF NOT EXISTS idx_leads_freelancer_field_bid
  ON leads (freelancer_field, status, posted_at)
  WHERE source = 'freelancer';
