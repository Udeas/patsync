-- Grant number and annuity tracking fields
ALTER TABLE patent_project ADD COLUMN IF NOT EXISTS grant_number VARCHAR;
ALTER TABLE patent_project ADD COLUMN IF NOT EXISTS annuity_paid_upto DATE;
ALTER TABLE patent_project ADD COLUMN IF NOT EXISTS next_annuity_due DATE;
