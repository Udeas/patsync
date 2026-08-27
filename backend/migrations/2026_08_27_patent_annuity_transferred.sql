-- Marks a docket's annuity/renewal tracking as transferred to another firm.
-- Once set, no further annuity reminders or payments are shown/accepted.
ALTER TABLE patent_project ADD COLUMN IF NOT EXISTS annuity_transferred_at TIMESTAMPTZ;
ALTER TABLE patent_project ADD COLUMN IF NOT EXISTS annuity_transferred_comment TEXT;
