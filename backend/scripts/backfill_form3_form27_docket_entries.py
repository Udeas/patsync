"""One-time backfill: create Form 3 (post-FER) and Form 27 docket entries for
patent projects that already had a FER date / grant date recorded *before*
the auto-docketing feature existed.

Both triggers (upsert_form3_updated_entry, upsert_form27_entry) only fire
on new FER/grant status_date entries going through update_project_detail /
update_status_event - they never ran retroactively for existing data. This
script re-runs the same idempotent upsert logic against every project's
current FER/grant status, so it's safe to run more than once (already-
existing docket entries are left untouched).

Usage:
    cd patsync/backend && .venv/bin/python scripts/backfill_form3_form27_docket_entries.py
"""

from __future__ import annotations

from sqlmodel import Session, select

from app.database import engine
from app.patents.models import PatentProject, PatentStatusEvent
from app.patents.patent_status_catalog import STATUS_ID_FER_ISSUED, STATUS_ID_GRANTED
from app.patents.service import upsert_form27_entry, upsert_form3_updated_entry


def _latest_status_date(session: Session, project_id: int, status_id: int):
    event = session.exec(
        select(PatentStatusEvent)
        .where(PatentStatusEvent.project_id == project_id, PatentStatusEvent.status_id == status_id)
        .order_by(PatentStatusEvent.id.desc())
    ).first()
    return event.status_date if event else None


def main() -> None:
    fer_processed = 0
    grant_processed = 0
    grant_skipped_no_number = 0

    with Session(engine) as session:
        projects = session.exec(select(PatentProject)).all()
        for project in projects:
            fer_date = _latest_status_date(session, project.id, STATUS_ID_FER_ISSUED)
            if fer_date:
                upsert_form3_updated_entry(session, project.id, fer_date)
                fer_processed += 1

            grant_date = _latest_status_date(session, project.id, STATUS_ID_GRANTED)
            if grant_date:
                if not (project.grant_number or "").strip():
                    grant_skipped_no_number += 1
                else:
                    upsert_form27_entry(session, project.id, grant_date, project.grant_number)
                    grant_processed += 1

        session.commit()

    print(f"Projects scanned: {len(projects)}")
    print(f"FER-triggered Form 3 entries processed (created or confirmed up to date): {fer_processed}")
    print(f"Grant-triggered Form 27 entries processed (created or confirmed up to date): {grant_processed}")
    if grant_skipped_no_number:
        print(f"Skipped (granted but no grant_number on file): {grant_skipped_no_number}")


if __name__ == "__main__":
    main()
