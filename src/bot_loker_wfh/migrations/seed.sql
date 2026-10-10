-- Idempotent defaults. Re-applied on every apply_schema() call.
INSERT INTO filters (id, role_keywords, exclusion_keywords, min_relevance_score, max_posting_age_days, no_response_after_days)
VALUES (
  'default',
  '["laravel", "flutter", "nestjs", "react", "python", "backend", "full stack", "fullstack", "mobile developer", "software engineer", "software developer", "web developer", "programmer"]',
  '["unpaid", "commission only", "equity only", "must relocate"]',
  0.65, 14, 21
) ON CONFLICT DO NOTHING;

INSERT INTO ats_registry (id, ats_name, host, mode, open_button_label) VALUES
  ('gh-1', 'Greenhouse', 'job-boards.greenhouse.io', 'auto_fill', NULL),
  ('gh-2', 'Greenhouse', 'boards.greenhouse.io', 'auto_fill', NULL),
  ('lv-1', 'Lever', 'jobs.lever.co', 'auto_fill', 'Apply for this job'),
  ('lv-2', 'Lever', 'jobs.eu.lever.co', 'auto_fill', 'Apply for this job'),
  ('ab-1', 'Ashby', 'jobs.ashbyhq.com', 'assist', 'Apply'),
  ('wk-1', 'Workable', 'apply.workable.com', 'assist', 'Apply for this job'),
  ('sr-1', 'SmartRecruiters', 'jobs.smartrecruiters.com', 'assist', 'I''m interested'),
  ('kb-1', 'Kalibrr', 'www.kalibrr.com', 'assist', 'Apply')
ON CONFLICT DO NOTHING;

INSERT INTO app_settings (key, value) VALUES ('scrape_interval_hours', '4') ON CONFLICT DO NOTHING;
