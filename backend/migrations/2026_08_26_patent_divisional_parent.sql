-- Divisional docket parent application reference
ALTER TABLE patent_project ADD COLUMN IF NOT EXISTS parent_project_id INTEGER REFERENCES patent_project(id);
ALTER TABLE patent_project ADD COLUMN IF NOT EXISTS parent_application_no VARCHAR;
ALTER TABLE patent_project ADD COLUMN IF NOT EXISTS parent_application_date DATE;
