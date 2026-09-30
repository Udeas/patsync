-- Free-form project notes shown on the docket detail screen, newest first.
CREATE TABLE IF NOT EXISTS patent_project_note (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES patent_project(id),
    note_text TEXT NOT NULL,
    created_date TIMESTAMPTZ NOT NULL DEFAULT now()
);
