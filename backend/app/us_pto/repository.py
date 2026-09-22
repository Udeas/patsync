from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlmodel import Session

from app.us_pto.config import (
    WORK_STATUS_CLOSED,
    WORK_STATUS_DONE,
    WORK_STATUS_PENDING,
    WORK_STATUS_UNDER_EXTENSION,
)
from app.us_pto.database import get_us_pto_engine
from app.us_pto.doc_code_rules import build_calendar_reminder_rules, list_doc_code_rules
from app.us_pto.doc_codes import code_requires_email_draft, get_tracked_doc_codes
from app.us_pto.due_dates import compute_due_dates
from app.us_pto.models import UsptoTracker


def normalize_doc_code(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_cell(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%m/%d/%Y")
    return str(value).strip()


def scrape_duplicate_key(doc_code: str, event_date: str) -> tuple[str, str]:
    return (normalize_doc_code(doc_code), normalize_cell(event_date))


def entry_key(
    docket_no: str, doc_code: str, event_date: str, application_no: str = ""
) -> tuple[str, str, str, str]:
    return (
        normalize_cell(docket_no),
        normalize_doc_code(doc_code),
        normalize_cell(event_date),
        normalize_cell(application_no),
    )


def _now() -> datetime:
    return datetime.utcnow()


def _format_due_date(value: date | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value) if value else None


def _parse_due_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _entry_to_dict(entry: UsptoTracker) -> dict:
    """Full row for automation steps."""
    return {
        "id": entry.id,
        "docket_no": entry.docket_no,
        "application_no": entry.application_no,
        "doc_code": entry.doc_code,
        "particulars": entry.particulars,
        "event_date": entry.event_date,
        "final_due_date": _format_due_date(entry.final_due_date),
        "calendar_event_ids": entry.calendar_event_ids,
        "template_status": entry.template_status,
        "work_status": entry.work_status,
        "closure_processed": entry.is_closure_done,
    }


def _normalize_work_status(value: str | None) -> str:
    return (value or "").strip() or WORK_STATUS_PENDING


def _is_done_status(value: str | None) -> bool:
    return _normalize_work_status(value).upper() == WORK_STATUS_DONE.upper()


def _is_closed_status(value: str | None) -> bool:
    return _normalize_work_status(value).upper() == WORK_STATUS_CLOSED.upper()


def _is_finished_status(value: str | None) -> bool:
    """Done and Closed both mean the row is wrapped up - either should pull it
    out of active-work queues (overdue/extension flagging, due-date recompute,
    calendar/draft automation)."""
    return _is_done_status(value) or _is_closed_status(value)


def _tracked_code_set() -> set[str]:
    tracked = {normalize_doc_code(c) for c in get_tracked_doc_codes()}
    tracked.update(rule.doc_code for rule in list_doc_code_rules())
    return tracked


def _entry_is_tracked(entry: UsptoTracker) -> bool:
    tracked = _tracked_code_set()
    if not tracked:
        return True
    return normalize_doc_code(entry.doc_code) in tracked


def _pending_row_summary(entry: UsptoTracker) -> dict:
    return {
        "id": entry.id,
        "docket_no": entry.docket_no,
        "application_no": entry.application_no or "",
        "doc_code": entry.doc_code,
        "event_date": entry.event_date,
    }


DOCKET_EXCLUDED_DOC_CODES = frozenset({"ABN"})


def _format_template_status_label(raw: str) -> str:
    template = (raw or "").strip()
    if not template:
        return ""
    lowered = template.lower()
    if lowered == "done":
        return "Draft created"
    if lowered == "not required":
        return "Not required"
    return template


def _entry_to_ui_dict(entry: UsptoTracker) -> dict:
    """Fields exposed to View US Dockets (matches legacy Streamlit grid)."""
    calendar_label = "Created" if (entry.calendar_event_ids or "").strip() else ""
    template_label = _format_template_status_label(entry.template_status)
    return {
        "id": entry.id,
        "docket_no": entry.docket_no,
        "application_no": entry.application_no or "",
        "doc_code": entry.doc_code,
        "particulars": entry.particulars,
        "event_date": entry.event_date,
        "final_due_date": _format_due_date(entry.final_due_date),
        "completion_date": _format_due_date(entry.completion_date),
        "comment": entry.comment or "",
        "calendar_status": calendar_label,
        "template_status": template_label,
        "work_status": _normalize_work_status(entry.work_status),
    }


_db_initialized = False


def init_db() -> None:
    """Runs schema migrations at most once per process. Called before nearly
    every repository operation as a defensive guard (this module can run
    standalone), but re-running the full migration DDL on every call - as
    happened before this cache was added - meant every single row insert
    re-executed ~60+ statements including ALTER TABLE/ALTER COLUMN calls
    that require ACCESS EXCLUSIVE locks, causing multi-row fetches to hang
    indefinitely under any lock contention. The app's own startup hook
    (app/main.py) already runs migrations once; this guard just prevents
    every subsequent call in this module from redoing that work."""
    global _db_initialized
    if _db_initialized:
        return
    from app.database import run_schema_migrations

    run_schema_migrations()
    _db_initialized = True


def count_entries() -> int:
    with Session(get_us_pto_engine()) as session:
        return int(session.exec(select(func.count()).select_from(UsptoTracker)).scalar_one())


def insert_entry(
    docket_no: str,
    application_no: str,
    doc_code: str,
    particulars: str,
    event_date: str,
) -> int | None:
    init_db()
    final_due_date_str, _due_rows = compute_due_dates(doc_code, event_date)
    key = entry_key(docket_no, doc_code, event_date, application_no)

    dup_key = scrape_duplicate_key(doc_code, event_date)

    with Session(get_us_pto_engine()) as session:
        existing = session.scalars(
            select(UsptoTracker).where(
                UsptoTracker.doc_code == dup_key[0],
                UsptoTracker.event_date == dup_key[1],
            )
        ).first()
        if existing:
            return None

        entry = UsptoTracker(
            docket_no=key[0],
            application_no=key[3],
            doc_code=key[1],
            particulars=normalize_cell(particulars),
            event_date=key[2],
            final_due_date=_parse_due_date(final_due_date_str),
            work_status=WORK_STATUS_PENDING,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry.id


def insert_entries_from_rows(rows: list[dict]) -> tuple[int, int]:
    inserted = 0
    skipped_duplicates = 0
    for row in rows:
        entry_id = insert_entry(
            row.get("Docket No.", ""),
            row.get("Application No.", ""),
            row.get("Doc Code", ""),
            row.get("Particulars", ""),
            row.get("Event Date", ""),
        )
        if entry_id is not None:
            inserted += 1
        else:
            skipped_duplicates += 1
    return inserted, skipped_duplicates


def recompute_due_dates_for_doc_code(doc_code: str) -> int:
    """Re-run compute_due_dates against every existing (non-Done) row for
    doc_code, e.g. after a DocCodeRule's months/extension changed and the
    user chose to apply that change retroactively rather than just to new
    entries going forward. Returns the number of rows whose final_due_date
    actually changed."""
    init_db()
    normalized = normalize_doc_code(doc_code)
    updated = 0
    with Session(get_us_pto_engine()) as session:
        rows = list(
            session.scalars(
                select(UsptoTracker).where(UsptoTracker.doc_code == normalized)
            ).all()
        )
        for entry in rows:
            if _is_finished_status(entry.work_status):
                continue
            final_due_date_str, _due_rows = compute_due_dates(entry.doc_code, entry.event_date)
            new_due = _parse_due_date(final_due_date_str)
            if new_due != entry.final_due_date:
                entry.final_due_date = new_due
                entry.updated_at = _now()
                session.add(entry)
                updated += 1
        if updated:
            session.commit()
    return updated


def get_entry(entry_id: int) -> dict | None:
    init_db()
    with Session(get_us_pto_engine()) as session:
        entry = session.get(UsptoTracker, entry_id)
        return _entry_to_dict(entry) if entry else None


def list_entries(*, doc_codes: list[str] | None = None) -> list[dict]:
    init_db()
    with Session(get_us_pto_engine()) as session:
        statement = select(UsptoTracker).order_by(UsptoTracker.id)
        if doc_codes:
            normalized = [normalize_doc_code(c) for c in doc_codes]
            statement = statement.where(UsptoTracker.doc_code.in_(normalized))
        rows = session.scalars(statement).all()
        return [_entry_to_dict(row) for row in rows]


def _apply_overdue_extension_updates(session: Session, rows: list[UsptoTracker]) -> bool:
    today = date.today()
    changed = False
    for entry in rows:
        if not entry.final_due_date or entry.final_due_date >= today:
            continue
        if _is_finished_status(entry.work_status):
            continue
        if entry.work_status != WORK_STATUS_UNDER_EXTENSION:
            entry.work_status = WORK_STATUS_UNDER_EXTENSION
            entry.updated_at = _now()
            session.add(entry)
            changed = True
    if changed:
        session.commit()
    return changed


def _is_closed_entry(entry: UsptoTracker) -> bool:
    return _is_finished_status(entry.work_status) and entry.completion_date is not None


def _sync_empty_work_status_to_pending(session: Session, rows: list[UsptoTracker]) -> None:
    changed = False
    for entry in rows:
        if (entry.work_status or "").strip():
            continue
        entry.work_status = WORK_STATUS_PENDING
        entry.updated_at = _now()
        session.add(entry)
        changed = True
    if changed:
        session.commit()


NOT_REQUIRED_TEMPLATE_STATUS = "Not required"


def sync_email_not_required_for_ineligible() -> int:
    """Mark template_status for tracked rows without a configured email template."""
    init_db()
    updated = 0
    with Session(get_us_pto_engine()) as session:
        rows = list(session.scalars(select(UsptoTracker).order_by(UsptoTracker.id)).all())
        for entry in rows:
            if not _entry_is_tracked(entry):
                continue
            if _is_finished_status(entry.work_status):
                continue
            if (entry.template_status or "").strip():
                continue
            if code_requires_email_draft(entry.doc_code):
                continue
            entry.template_status = NOT_REQUIRED_TEMPLATE_STATUS
            entry.updated_at = _now()
            session.add(entry)
            updated += 1
        if updated:
            session.commit()
    return updated


def list_visible_doc_codes() -> list[str]:
    """Doc codes for the View US Dockets filter dropdown - restricted to codes
    that can actually appear as a row there: present in uspto_tracker, tracked
    (via doc_codes.yaml or a doc_code_rule - same set list_entries_for_ui
    filters by), and not explicitly excluded (e.g. ABN)."""
    init_db()
    tracked = _tracked_code_set()
    with Session(get_us_pto_engine()) as session:
        rows = session.scalars(select(UsptoTracker.doc_code).distinct()).all()
    codes = {normalize_doc_code(c) for c in rows if c}
    if tracked:
        codes &= tracked
    codes -= DOCKET_EXCLUDED_DOC_CODES
    return sorted(codes)


def list_entries_for_ui(
    *,
    project_code: str = "",
    doc_code: str = "",
    work_status: str = "",
    closed: bool = False,
) -> list[dict]:
    init_db()
    with Session(get_us_pto_engine()) as session:
        statement = select(UsptoTracker).order_by(UsptoTracker.id)
        tracked = _tracked_code_set()
        if tracked:
            statement = statement.where(UsptoTracker.doc_code.in_(tracked))
        rows = list(session.scalars(statement).all())
        rows = [
            row
            for row in rows
            if normalize_doc_code(row.doc_code) not in DOCKET_EXCLUDED_DOC_CODES
        ]
        if not closed:
            _sync_empty_work_status_to_pending(session, rows)
            if _apply_overdue_extension_updates(session, rows):
                rows = list(session.scalars(statement).all())
                rows = [
                    row
                    for row in rows
                    if normalize_doc_code(row.doc_code) not in DOCKET_EXCLUDED_DOC_CODES
                ]

        if closed:
            rows = [row for row in rows if _is_closed_entry(row)]
        else:
            rows = [row for row in rows if not _is_closed_entry(row)]

        entries = [_entry_to_ui_dict(row) for row in rows]

    if project_code:
        needle = project_code.strip().lower()
        entries = [
            e
            for e in entries
            if needle in e["docket_no"].lower()
            or needle in (e.get("application_no") or "").lower()
        ]
    if doc_code:
        needle = doc_code.strip().lower()
        entries = [e for e in entries if needle in e["doc_code"].lower()]
    if work_status and work_status != "All":
        entries = [e for e in entries if e.get("work_status") == work_status]
    return entries


def update_entry(entry_id: int, **fields: Any) -> None:
    if not fields:
        return
    init_db()
    with Session(get_us_pto_engine()) as session:
        entry = session.get(UsptoTracker, entry_id)
        if not entry:
            return
        for key, value in fields.items():
            if key == "closure_processed":
                entry.is_closure_done = bool(value)
            elif key == "is_closure_done":
                entry.is_closure_done = bool(value)
            elif hasattr(entry, key):
                setattr(entry, key, value)
        entry.updated_at = _now()
        session.add(entry)
        session.commit()


def update_work_status(entry_id: int, work_status: str) -> None:
    update_entry(entry_id, work_status=work_status)


def update_work_status_batch(
    updates: dict[int, str],
    completion_dates: dict[int, str] | None = None,
    comments: dict[int, str] | None = None,
) -> None:
    init_db()
    completion_dates = completion_dates or {}
    comments = comments or {}
    with Session(get_us_pto_engine()) as session:
        for entry_id, status in updates.items():
            entry = session.get(UsptoTracker, entry_id)
            if not entry:
                continue
            entry.work_status = status
            if _is_finished_status(status):
                raw_date = completion_dates.get(entry_id)
                if raw_date:
                    entry.completion_date = _parse_due_date(raw_date)
            if entry_id in comments:
                entry.comment = comments[entry_id]
            entry.updated_at = _now()
            session.add(entry)
        session.commit()


def get_automation_pending() -> dict:
    init_db()
    sync_email_not_required_for_ineligible()
    calendar_pending: list[dict] = []
    email_pending: list[dict] = []

    with Session(get_us_pto_engine()) as session:
        rows = list(session.scalars(select(UsptoTracker).order_by(UsptoTracker.id)).all())

    for entry in rows:
        if not _entry_is_tracked(entry):
            continue
        if _is_finished_status(entry.work_status):
            continue

        if not (entry.calendar_event_ids or "").strip():
            calendar_pending.append(_pending_row_summary(entry))

        if code_requires_email_draft(entry.doc_code) and not (entry.template_status or "").strip():
            email_pending.append(_pending_row_summary(entry))

    return {
        "calendar_pending": calendar_pending,
        "email_pending": email_pending,
        "calendar_count": len(calendar_pending),
        "email_count": len(email_pending),
    }


def list_calendar_candidates(*, duplicate_mode: str = "all") -> list[dict]:
    from app.us_pto.doc_codes import get_rules_for_tracked_doc_code

    init_db()
    entries = list_entries()
    db_rules_by_code = {rule.doc_code: rule for rule in list_doc_code_rules()}
    candidates: list[dict] = []
    accepted_keys: set[tuple[str, str]] = set()

    for entry in entries:
        doc_code = normalize_doc_code(entry["doc_code"])
        db_rule = db_rules_by_code.get(doc_code)
        if db_rule:
            rules = build_calendar_reminder_rules(db_rule)
            rule_source = "doc_code_rule"
        else:
            rules = get_rules_for_tracked_doc_code(doc_code)
            rule_source = "legacy"
        if not rules:
            continue
        if entry.get("calendar_event_ids"):
            continue
        if _is_finished_status(entry.get("work_status")):
            continue

        dup_key = (doc_code, normalize_cell(entry["event_date"]))
        if duplicate_mode == "one":
            if dup_key in accepted_keys:
                continue
            accepted_keys.add(dup_key)

        row_data = {
            "Docket No.": entry["docket_no"],
            "Application No.": entry["application_no"],
            "Doc Code": entry["doc_code"],
            "Particulars": entry["particulars"],
            "Event Date": entry["event_date"],
        }
        candidates.append(
            {
                "entry_id": entry["id"],
                "row_data": row_data,
                "rules": rules,
                "rule_source": rule_source,
            }
        )
    return candidates


def list_draft_candidates() -> list[dict]:
    init_db()
    sync_email_not_required_for_ineligible()
    entries = list_entries()
    tracked = _tracked_code_set()
    results: list[dict] = []
    for entry in entries:
        doc_code = normalize_doc_code(entry["doc_code"])
        if tracked and doc_code not in tracked:
            continue
        if not code_requires_email_draft(doc_code):
            continue
        if _is_finished_status(entry.get("work_status")):
            continue
        if entry.get("template_status"):
            continue
        results.append(entry)
    return results


def list_done_entries_for_closure(
    *, entry_ids: list[int] | None = None, weekly: bool = False
) -> list[dict]:
    init_db()
    with Session(get_us_pto_engine()) as session:
        statement = select(UsptoTracker).where(
            func.upper(UsptoTracker.work_status) == "DONE",
            UsptoTracker.calendar_event_ids != "",
        )
        if entry_ids:
            statement = statement.where(UsptoTracker.id.in_(entry_ids))
        elif weekly:
            statement = statement.where(UsptoTracker.is_closure_done.is_(False))
        rows = session.scalars(statement).all()
        return [_entry_to_dict(row) for row in rows]


def mark_closure_processed(entry_id: int) -> None:
    update_entry(entry_id, is_closure_done=True)
