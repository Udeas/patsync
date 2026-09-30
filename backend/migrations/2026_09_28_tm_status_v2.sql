-- Trademark Status Model v2: informative sub-status label (replaces the
-- one-off is_under_hearing flag), plus an optional free-text note per
-- timeline row (used for the Accepted/Registered Journal No. box).
ALTER TABLE tm_application_data ADD COLUMN IF NOT EXISTS sub_status TEXT;
ALTER TABLE tm_application_state ADD COLUMN IF NOT EXISTS note TEXT;

UPDATE tm_application_data SET sub_status = 'Under Hearing' WHERE is_under_hearing = TRUE;
