-- Add completion_date for closed US PTO docket rows
ALTER TABLE uspto_tracker ADD COLUMN IF NOT EXISTS completion_date DATE;
