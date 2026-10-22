"""A tracker row can need multiple Google Calendar reminder events (one per
docket rule). If one insert in the middle of that loop fails (rate limit,
transient API error, etc.), the events already created for earlier rules
must still be persisted to calendar_event_ids immediately - otherwise the
row keeps showing as "pending" and gets ALL of its reminders re-created
(duplicated on the live calendar) on the next run. See
app/us_pto/steps/calendar_events.py:create_events_for_candidates.
"""

from sqlmodel import Session

from app.us_pto import repository
from app.us_pto.database import get_us_pto_engine
from app.us_pto.models import UsptoTracker
from app.us_pto.repository import list_calendar_candidates
from app.us_pto.steps.calendar_events import create_events_for_candidates


def _insert_entry(**overrides) -> int:
    repository.init_db()
    defaults = dict(
        docket_no="ZZZ-CALPF-001",
        application_no="90000001",
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


class _FakeInsertCall:
    def __init__(self, outcome):
        self._outcome = outcome

    def execute(self):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _FakeEvents:
    def __init__(self, outcomes):
        self._outcomes = outcomes
        self._call_index = 0

    def insert(self, calendarId, body):  # noqa: N803 - matches Google API signature
        outcome = self._outcomes[self._call_index]
        self._call_index += 1
        return _FakeInsertCall(outcome)


class _FakeCalendarService:
    """Returns a fixed sequence of insert() outcomes across calls, in order."""

    def __init__(self, outcomes):
        self._events = _FakeEvents(outcomes)

    def events(self):
        return self._events


def test_partial_failure_persists_already_created_event_ids(monkeypatch):
    entry_id = _insert_entry(doc_code="CTNF", event_date="01/01/2027", docket_no="ZZZ-CALPF-001", application_no="90000001")

    candidate = {
        "entry_id": entry_id,
        "row_data": {
            "Docket No.": "ZZZ-CALPF-001",
            "Application No.": "90000001",
            "Doc Code": "CTNF",
            "Particulars": "Non-Final Rejection",
            "Event Date": "01/01/2027",
        },
        "rules": [
            (1, "1st Month Deadline", 3),
            (2, "2nd Month Deadline", 3),
            (3, "3rd Month Deadline", 3),
        ],
        "rule_source": "legacy",
    }

    # 1st insert succeeds, 2nd raises (simulating a transient API error),
    # 3rd succeeds.
    service = _FakeCalendarService(
        outcomes=[
            {"id": "gcal-event-1"},
            RuntimeError("rate limit exceeded"),
            {"id": "gcal-event-3"},
        ]
    )

    created_rows, failed_rows = create_events_for_candidates(service, [candidate])

    # The row shows up in both lists: it's a partial success.
    assert len(created_rows) == 1
    assert len(failed_rows) == 1
    assert failed_rows[0]["entry_id"] == entry_id
    assert "2nd Month Deadline" in failed_rows[0]["error"]

    # Both successfully-created IDs are persisted, in order, even though the
    # 2nd rule failed in between them.
    assert created_rows[0]["calendar_event_ids"] == "gcal-event-1 | gcal-event-3"

    with Session(get_us_pto_engine()) as session:
        entry = session.get(UsptoTracker, entry_id)
        assert entry.calendar_event_ids == "gcal-event-1 | gcal-event-3"
        assert "failed" in entry.calendar_status.lower()

    # Root-cause regression check: because calendar_event_ids is now
    # non-empty, the row must stop being offered as a "pending" candidate -
    # otherwise the 1st/3rd events would be duplicated on the next run.
    monkeypatch.setattr(repository, "_tracked_code_set", lambda rules=None: {"CTNF"})
    monkeypatch.setattr(
        "app.us_pto.doc_codes.get_rules_for_tracked_doc_code",
        lambda code: [(1, "1st Month Deadline", 3)],
    )
    remaining_candidates = list_calendar_candidates()
    assert entry_id not in {c["entry_id"] for c in remaining_candidates}


def test_full_failure_persists_nothing_and_stays_pending(monkeypatch):
    entry_id = _insert_entry(doc_code="CTNF", event_date="02/02/2027", docket_no="ZZZ-CALPF-002", application_no="90000002")

    candidate = {
        "entry_id": entry_id,
        "row_data": {
            "Docket No.": "ZZZ-CALPF-002",
            "Application No.": "90000002",
            "Doc Code": "CTNF",
            "Particulars": "Non-Final Rejection",
            "Event Date": "02/02/2027",
        },
        "rules": [(1, "1st Month Deadline", 3)],
        "rule_source": "legacy",
    }

    service = _FakeCalendarService(outcomes=[RuntimeError("network error")])

    created_rows, failed_rows = create_events_for_candidates(service, [candidate])

    assert created_rows == []
    assert len(failed_rows) == 1

    with Session(get_us_pto_engine()) as session:
        entry = session.get(UsptoTracker, entry_id)
        assert entry.calendar_event_ids == ""

    monkeypatch.setattr(repository, "_tracked_code_set", lambda rules=None: {"CTNF"})
    monkeypatch.setattr(
        "app.us_pto.doc_codes.get_rules_for_tracked_doc_code",
        lambda code: [(1, "1st Month Deadline", 3)],
    )
    remaining_candidates = list_calendar_candidates()
    assert entry_id in {c["entry_id"] for c in remaining_candidates}


def test_full_success_matches_previous_behavior(monkeypatch):
    entry_id = _insert_entry(doc_code="CTNF", event_date="03/03/2027", docket_no="ZZZ-CALPF-003", application_no="90000003")

    candidate = {
        "entry_id": entry_id,
        "row_data": {
            "Docket No.": "ZZZ-CALPF-003",
            "Application No.": "90000003",
            "Doc Code": "CTNF",
            "Particulars": "Non-Final Rejection",
            "Event Date": "03/03/2027",
        },
        "rules": [(1, "1st Month Deadline", 3), (2, "2nd Month Deadline", 3)],
        "rule_source": "legacy",
    }

    service = _FakeCalendarService(outcomes=[{"id": "gcal-event-a"}, {"id": "gcal-event-b"}])

    created_rows, failed_rows = create_events_for_candidates(service, [candidate])

    assert failed_rows == []
    assert len(created_rows) == 1
    assert created_rows[0]["calendar_event_ids"] == "gcal-event-a | gcal-event-b"

    with Session(get_us_pto_engine()) as session:
        entry = session.get(UsptoTracker, entry_id)
        assert entry.calendar_event_ids == "gcal-event-a | gcal-event-b"
        assert entry.calendar_status == "Event Created with 1st Month Deadline, 2nd Month Deadline"
