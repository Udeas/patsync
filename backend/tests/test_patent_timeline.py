"""Domain rules for patent FER/hearing reminders (Phase 1: computed only)."""

from datetime import date, timedelta

from app.domain.patent_timeline import add_six_calendar_months, build_timeline_for_application
from app.status_catalog import (
    STATUS_APPLICATION_FILED,
    STATUS_CASE_UNDER_HEARING,
    STATUS_FER_ISSUED,
    STATUS_FER_RESPONSE_SUBMITTED,
    STATUS_SECRECY_DIRECTIONS,
)


def test_add_six_calendar_months_aug31():
    """Aug 31 + 6 months clamps to last day of February."""
    assert add_six_calendar_months(date(2024, 8, 31)) == date(2025, 2, 28)


def test_add_six_calendar_months_jan15():
    assert add_six_calendar_months(date(2024, 1, 15)) == date(2024, 7, 15)


def test_fer_reminders_only_when_status_fer_issued():
    filing = date(2025, 1, 1)
    deadline = add_six_calendar_months(filing)
    states = [
        (1, filing, STATUS_APPLICATION_FILED),
        (2, date(2025, 2, 1), STATUS_FER_ISSUED),
    ]
    tl = build_timeline_for_application(
        states_ordered=states,
        current_status_name=STATUS_FER_ISSUED,
        today=date(2025, 6, 1),
    )
    assert tl.fer_response_deadline == deadline
    assert any(r.kind == "fer_deadline" for r in tl.upcoming_reminders)


def test_no_fer_reminders_under_secrecy():
    filing = date(2025, 1, 1)
    states = [
        (1, filing, STATUS_APPLICATION_FILED),
        (2, date(2025, 3, 1), STATUS_SECRECY_DIRECTIONS),
    ]
    tl = build_timeline_for_application(
        states_ordered=states,
        current_status_name=STATUS_SECRECY_DIRECTIONS,
        today=date(2025, 5, 1),
    )
    assert tl.fer_response_deadline == add_six_calendar_months(filing)
    assert tl.upcoming_reminders == []


def test_no_fer_reminders_after_response_submitted():
    filing = date(2025, 1, 1)
    states = [
        (1, filing, STATUS_APPLICATION_FILED),
        (2, date(2025, 2, 1), STATUS_FER_ISSUED),
        (3, date(2025, 6, 1), STATUS_FER_RESPONSE_SUBMITTED),
    ]
    tl = build_timeline_for_application(
        states_ordered=states,
        current_status_name=STATUS_FER_RESPONSE_SUBMITTED,
        today=date(2025, 6, 15),
    )
    assert not any(r.kind == "fer_deadline" for r in tl.upcoming_reminders)


def test_hearing_reminders_include_on_day():
    hearing = date(2025, 10, 20)
    states = [
        (1, date(2025, 1, 1), STATUS_APPLICATION_FILED),
        (2, date(2025, 5, 1), STATUS_FER_ISSUED),
        (3, date(2025, 7, 1), STATUS_FER_RESPONSE_SUBMITTED),
        (4, hearing, STATUS_CASE_UNDER_HEARING),
    ]
    tl = build_timeline_for_application(
        states_ordered=states,
        current_status_name=STATUS_CASE_UNDER_HEARING,
        today=date(2025, 10, 1),
    )
    fire_dates = [r.fire_on for r in tl.upcoming_reminders if r.kind == "hearing"]
    assert hearing in fire_dates
    assert hearing - timedelta(days=3) in fire_dates
