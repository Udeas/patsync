-- US PTO docket automation (tracker_db only)
CREATE TABLE IF NOT EXISTS uspto_tracker (
    id SERIAL PRIMARY KEY,
    docket_no VARCHAR(64) NOT NULL,
    application_no VARCHAR(32) NOT NULL DEFAULT '',
    doc_code VARCHAR(32) NOT NULL,
    particulars TEXT NOT NULL DEFAULT '',
    event_date VARCHAR(16) NOT NULL,
    final_due_date DATE,
    work_status VARCHAR(32) NOT NULL DEFAULT 'Pending',
    calendar_event_ids TEXT NOT NULL DEFAULT '',
    template_status VARCHAR(64) NOT NULL DEFAULT '',
    is_closure_done BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_uspto_tracker_natural_key
        UNIQUE (docket_no, doc_code, event_date, application_no)
);

CREATE INDEX IF NOT EXISTS ix_uspto_tracker_doc_code ON uspto_tracker (doc_code);
CREATE INDEX IF NOT EXISTS ix_uspto_tracker_work_status ON uspto_tracker (work_status);
CREATE INDEX IF NOT EXISTS ix_uspto_tracker_docket_no ON uspto_tracker (docket_no);
