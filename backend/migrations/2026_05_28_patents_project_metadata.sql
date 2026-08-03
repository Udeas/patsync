-- Patent project metadata and PCT international applications
ALTER TABLE patent_project ADD COLUMN IF NOT EXISTS application_type VARCHAR;
ALTER TABLE patent_project ADD COLUMN IF NOT EXISTS provisional_kind VARCHAR(3);

CREATE TABLE IF NOT EXISTS patent_international_application (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES patent_project(id),
  international_application_no VARCHAR NOT NULL,
  international_application_date DATE NOT NULL
);
