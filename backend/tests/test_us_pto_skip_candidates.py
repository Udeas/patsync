"""User-rejected rows (unchecked in the Step 2/3 confirm table) must be marked
with a persisted Skipped status so they stop reappearing in future preview
candidates and in the /automation/pending notification list - without the
user having to configure a doc-code rule or email template."""

from unittest.mock import MagicMock

from sqlmodel import Session

from app.us_pto import repository
from app.us_pto.database import get_us_pto_engine
from app.us_pto.models import UsptoTracker
from app.us_pto.repository import (
    SKIPPED_CALENDAR_STATUS,
    SKIPPED_TEMPLATE_STATUS,
    get_automation_pending,
    list_calendar_candidates,
)
from app.us_pto.steps import calendar_events, email_drafts


def _insert_entry(**overrides) -> int:
    repository.init_db()
    defaults = dict(
        docket_no="ABC-P001",
        application_no="12345678",
        doc_code="CTNF",
        particulars="Non-Final Rejection",
        event_date="08/28/2026",
        work_status="Pending",
    )
    defaults.update(overrides)
    with Session(get_us_pto_engine()) as session:
        entry = UsptoTracker(**defaults)
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry.id


def test_list_calendar_candidates_excludes_skipped_rows(monkeypatch):
    monkeypatch.setattr(repository, "_tracked_code_set", lambda rules=None: {"CTNF"})
    monkeypatch.setattr(
        "app.us_pto.doc_codes.get_rules_for_tracked_doc_code",
        lambda code: [(1, "1st Month Deadline", 3)],
    )

    pending_id = _insert_entry(doc_code="CTNF", event_date="01/01/2026")
    skipped_id = _insert_entry(
        doc_code="CTNF", event_date="02/02/2026", calendar_status=SKIPPED_CALENDAR_STATUS
    )

    candidates = list_calendar_candidates()
    entry_ids = {c["entry_id"] for c in candidates}

    assert pending_id in entry_ids
    assert skipped_id not in entry_ids


def test_get_automation_pending_excludes_skipped_rows(monkeypatch):
    monkeypatch.setattr(repository, "_tracked_code_set", lambda rules=None: {"CTNF"})
    monkeypatch.setattr(
        "app.us_pto.repository.code_requires_email_draft",
        lambda code, **kwargs: True,
    )

    calendar_skipped_id = _insert_entry(
        doc_code="CTNF", event_date="03/03/2026", calendar_status=SKIPPED_CALENDAR_STATUS
    )
    email_skipped_id = _insert_entry(
        doc_code="CTNF", event_date="04/04/2026", template_status=SKIPPED_TEMPLATE_STATUS
    )
    untouched_id = _insert_entry(doc_code="CTNF", event_date="05/05/2026")

    pending = get_automation_pending()
    calendar_ids = {row["id"] for row in pending["calendar_pending"]}
    email_ids = {row["id"] for row in pending["email_pending"]}

    assert calendar_skipped_id not in calendar_ids
    assert email_skipped_id not in email_ids
    assert untouched_id in calendar_ids
    assert untouched_id in email_ids


def test_create_events_for_ui_skips_excluded_ids(monkeypatch):
    kept_id = _insert_entry(doc_code="CTNF", event_date="06/06/2026")
    excluded_id = _insert_entry(doc_code="CTNF", event_date="07/07/2026")

    fake_candidates = [
        {"entry_id": kept_id, "row_data": {}, "rules": [(1, "x", 1)], "rule_source": "legacy"},
        {"entry_id": excluded_id, "row_data": {}, "rules": [(1, "x", 1)], "rule_source": "legacy"},
    ]
    monkeypatch.setattr(calendar_events, "list_calendar_candidates", lambda **kw: fake_candidates)
    monkeypatch.setattr(calendar_events, "get_calendar_service", lambda: MagicMock())

    seen_entry_ids = []

    def fake_create_events_for_candidates(service, candidates, *, job=None):
        seen_entry_ids.extend(c["entry_id"] for c in candidates)
        return [], []

    monkeypatch.setattr(
        calendar_events, "create_events_for_candidates", fake_create_events_for_candidates
    )

    result = calendar_events.create_events_for_ui("all", excluded_entry_ids={excluded_id})

    assert seen_entry_ids == [kept_id]
    assert result["skipped_count"] == 1

    with Session(get_us_pto_engine()) as session:
        skipped_entry = session.get(UsptoTracker, excluded_id)
        assert skipped_entry.calendar_status == SKIPPED_CALENDAR_STATUS


def test_create_drafts_for_ui_skips_excluded_ids(monkeypatch):
    kept = {"id": 101, "docket_no": "ABC-P002", "doc_code": "CTNF"}
    excluded = {"id": 102, "docket_no": "ABC-P003", "doc_code": "CTNF"}
    monkeypatch.setattr(email_drafts, "list_draft_candidates", lambda: [kept, excluded])
    monkeypatch.setattr(email_drafts, "get_gmail_service", lambda: MagicMock())

    seen_ids = []

    def fake_process_entries(entries, service, *, job=None):
        seen_ids.extend(e["id"] for e in entries)
        return 0, 0, 0

    monkeypatch.setattr(email_drafts, "process_entries", fake_process_entries)

    captured_updates = {}

    def fake_update_entry(entry_id, **fields):
        captured_updates[entry_id] = fields

    monkeypatch.setattr(email_drafts, "update_entry", fake_update_entry)

    result = email_drafts.create_drafts_for_ui(excluded_entry_ids={excluded["id"]})

    assert seen_ids == [kept["id"]]
    assert result["skipped_count"] == 1
    assert captured_updates[excluded["id"]] == {"template_status": SKIPPED_TEMPLATE_STATUS}
