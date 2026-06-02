-- Add client/attorney references to design and trademark project tables
ALTER TABLE application_data ADD COLUMN IF NOT EXISTS client_id INTEGER;
ALTER TABLE application_data ADD COLUMN IF NOT EXISTS attorney_id INTEGER;

ALTER TABLE tm_application_data ADD COLUMN IF NOT EXISTS client_id INTEGER;
ALTER TABLE tm_application_data ADD COLUMN IF NOT EXISTS attorney_id INTEGER;
