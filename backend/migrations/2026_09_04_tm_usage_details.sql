-- TM Create screen: capture whether the mark is "Proposed to be used" or
-- already "Used since" a given date, alongside the trademark project.
ALTER TABLE tm_application_data ADD COLUMN IF NOT EXISTS tm_usage_status TEXT;
ALTER TABLE tm_application_data ADD COLUMN IF NOT EXISTS tm_used_since_date DATE;
