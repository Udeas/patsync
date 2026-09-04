"""Domain rules for trademark FER/hearing/renewal reminders."""

from datetime import date, timedelta

from app.domain.tm_timeline import add_one_calendar_month, add_years, build_timeline_for_tm_application
from app.tm_status_catalog import (
    STATUS_TM_APPLICATION_FILED,
    STATUS_TM_FER_ISSUED,
    STATUS_TM_HEARING,
    STATUS_TM_REGISTERED,
)


def test_add_one_calendar_month_jan31():
    assert add_one_calendar_month(date(2025, 1, 31)) == date(2025, 2, 28)


def test_fer_followup_reminder_one_month_after_fer_issued():
    fer_date = date(2025, 3, 15)
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, fer_date, STATUS_TM_FER_ISSUED),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_FER_ISSUED,
        today=date(2025, 3, 20),
    )
    assert tl.fer_followup_due == add_one_calendar_month(fer_date)
    assert len(tl.upcoming_reminders) == 1
    assert tl.upcoming_reminders[0].kind == "fer_followup"
    assert tl.upcoming_reminders[0].fire_on == add_one_calendar_month(fer_date)


def test_no_fer_reminder_after_leaving_fer_status():
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, date(2025, 3, 1), STATUS_TM_FER_ISSUED),
        (3, date(2025, 4, 1), "FER Response Submitted"),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name="FER Response Submitted",
        today=date(2025, 4, 5),
    )
    assert not any(r.kind == "fer_followup" for r in tl.upcoming_reminders)


def test_hearing_reminder_three_days_before():
    hearing = date(2025, 10, 20)
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, date(2025, 5, 1), STATUS_TM_FER_ISSUED),
        (3, date(2025, 7, 1), "FER Response Submitted"),
        (4, hearing, STATUS_TM_HEARING),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_HEARING,
        today=date(2025, 10, 1),
    )
    fire_dates = [r.fire_on for r in tl.upcoming_reminders if r.kind == "hearing"]
    assert hearing - timedelta(days=3) in fire_dates
    assert len([r for r in tl.upcoming_reminders if r.kind == "hearing"]) == 1


def test_add_years_leap_day_clamps_to_feb_28():
    assert add_years(date(2024, 2, 29), 10) == date(2034, 2, 28)


def test_renewal_reminder_ten_years_after_filing_once_registered():
    filing = date(2015, 6, 10)
    states = [
        (1, filing, STATUS_TM_APPLICATION_FILED),
        (2, date(2016, 1, 1), STATUS_TM_REGISTERED),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_REGISTERED,
        today=date(2026, 1, 1),
    )
    assert tl.renewal_due == add_years(filing, 10) == date(2025, 6, 10)
    assert len(tl.upcoming_reminders) == 1
    assert tl.upcoming_reminders[0].kind == "renewal"
    assert tl.upcoming_reminders[0].fire_on == date(2025, 6, 10)


def test_renewal_reminder_still_shows_when_overdue():
    filing = date(2010, 1, 1)
    states = [
        (1, filing, STATUS_TM_APPLICATION_FILED),
        (2, date(2010, 6, 1), STATUS_TM_REGISTERED),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_REGISTERED,
        today=date(2026, 1, 1),
    )
    assert tl.renewal_due == date(2020, 1, 1)
    assert any(r.kind == "renewal" for r in tl.upcoming_reminders)


def test_no_renewal_reminder_before_registered():
    filing = date(2015, 6, 10)
    states = [
        (1, filing, STATUS_TM_APPLICATION_FILED),
        (2, date(2016, 1, 1), "FER Issued"),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name="FER Issued",
        today=date(2016, 2, 1),
    )
    assert not any(r.kind == "renewal" for r in tl.upcoming_reminders)
