"""One-time rebuild: clear all US docket entries (uspto_tracker) and re-import
them from the Tracker_Updates mailbox, scanning every message received on or
after a given date regardless of its \\Seen flag.

This is for the "start fresh" case - normal day-to-day polling should keep
using Step 1 (run_fetch_for_ui / fetch_emails), which only looks at UNSEEN
mail. Once the table is cleared, everything in the mailbox is already marked
\\Seen from prior runs, so that incremental path would find nothing.

doc_code_rules (calendar/email config) is left untouched - only the
uspto_tracker rows are cleared and rebuilt.

Usage:
    cd patsync/backend && .venv/bin/python scripts/rebuild_uspto_docket_from_email.py 2026-03-01
"""

from __future__ import annotations

import sys
from datetime import date

from sqlmodel import Session, delete

from app.database import engine
from app.us_pto.models import UsptoTracker
from app.us_pto.repository import init_db, insert_entries_from_rows
from app.us_pto.steps.fetch_email import fetch_emails_since


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: rebuild_uspto_docket_from_email.py YYYY-MM-DD")
        sys.exit(1)
    since_date = date.fromisoformat(sys.argv[1])

    init_db()

    with Session(engine) as session:
        deleted = session.exec(delete(UsptoTracker))
        session.commit()
        print(f"Cleared uspto_tracker: {deleted.rowcount} row(s) deleted.")

    rows, unparsed_count = fetch_emails_since(since_date)
    print(f"Scanned mailbox since {since_date.isoformat()}: parsed {len(rows)} row(s) "
          f"from matching emails; {unparsed_count} email(s) had no recognizable office-action content.")

    inserted, skipped_duplicates = insert_entries_from_rows(rows)
    print(f"Inserted {inserted} row(s); skipped {skipped_duplicates} duplicate(s).")

    doc_codes = sorted({str(r.get("Doc Code", "")).strip().upper() for r in rows if r.get("Doc Code")})
    print(f"Distinct doc codes seen ({len(doc_codes)}): {', '.join(doc_codes)}")


if __name__ == "__main__":
    main()
