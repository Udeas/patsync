"""Domain rules for trademark FER/hearing/renewal reminders."""

from datetime import date, timedelta

from app.domain.tm_timeline import (
    add_months,
    add_one_calendar_month,
    add_years,
    build_timeline_for_tm_application,
)
from app.tm_status_catalog import (
    STATUS_TM_ACCEPTED_ADVERTISED,
    STATUS_TM_APPLICATION_FILED,
    STATUS_TM_FER_ISSUED,
    STATUS_TM_FORMALITY_FAIL,
    STATUS_TM_FORMALITY_FAIL_RESPONSE,
    STATUS_TM_HEARING,
    STATUS_TM_NOTICE_132_ISSUED,
    STATUS_TM_NOTICE_132_RESPONSE,
    STATUS_TM_REGISTERED,
    STATUS_TM_RENEWED,
    STATUS_TM_WRITTEN_RESPONSE_TO_HEARING,
)


def test_add_one_calendar_month_jan31():
    assert add_one_calendar_month(date(2025, 1, 31)) == date(2025, 2, 28)


def test_formality_fail_followup_reminder_one_month_after_formality_fail():
    fail_date = date(2025, 3, 15)
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, fail_date, STATUS_TM_FORMALITY_FAIL),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_FORMALITY_FAIL,
        today=date(2025, 3, 20),
    )
    assert tl.formality_fail_followup_due == add_one_calendar_month(fail_date)
    assert len(tl.upcoming_reminders) == 1
    assert tl.upcoming_reminders[0].kind == "formality_fail_followup"
    assert tl.upcoming_reminders[0].fire_on == add_one_calendar_month(fail_date)


def test_no_formality_fail_reminder_after_response_filed():
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, date(2025, 3, 1), STATUS_TM_FORMALITY_FAIL),
        (3, date(2025, 3, 20), STATUS_TM_FORMALITY_FAIL_RESPONSE),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_FORMALITY_FAIL_RESPONSE,
        today=date(2025, 4, 1),
    )
    assert not any(r.kind == "formality_fail_followup" for r in tl.upcoming_reminders)


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


def test_fer_reminder_still_shows_when_overdue():
    fer_date = date(2025, 3, 15)
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, fer_date, STATUS_TM_FER_ISSUED),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_FER_ISSUED,
        today=date(2026, 1, 1),
    )
    assert tl.fer_followup_due == add_one_calendar_month(fer_date)
    assert any(r.kind == "fer_followup" for r in tl.upcoming_reminders)


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


def test_notice_132_followup_reminder_one_month_after_issued():
    notice_date = date(2025, 3, 15)
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, notice_date, STATUS_TM_NOTICE_132_ISSUED),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_NOTICE_132_ISSUED,
        today=date(2025, 3, 20),
    )
    assert tl.notice_132_followup_due == add_one_calendar_month(notice_date)
    assert len(tl.upcoming_reminders) == 1
    assert tl.upcoming_reminders[0].kind == "notice_132_followup"


def test_no_notice_132_reminder_after_response_filed():
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, date(2025, 3, 1), STATUS_TM_NOTICE_132_ISSUED),
        (3, date(2025, 3, 20), STATUS_TM_NOTICE_132_RESPONSE),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_NOTICE_132_RESPONSE,
        today=date(2025, 4, 1),
    )
    assert not any(r.kind == "notice_132_followup" for r in tl.upcoming_reminders)


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


def test_hearing_reminder_still_shows_when_overdue():
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
        today=date(2026, 1, 1),
    )
    fire_dates = [r.fire_on for r in tl.upcoming_reminders if r.kind == "hearing"]
    assert hearing - timedelta(days=3) in fire_dates


def test_hearing_response_due_fifteen_days_after_hearing():
    hearing = date(2025, 10, 20)
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, hearing, STATUS_TM_HEARING),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_HEARING,
        today=date(2025, 10, 21),
    )
    assert tl.hearing_response_due == hearing + timedelta(days=15)
    assert any(r.kind == "hearing_response" and r.fire_on == hearing + timedelta(days=15) for r in tl.upcoming_reminders)


def test_no_hearing_reminders_after_written_response_submitted():
    hearing = date(2025, 10, 20)
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, hearing, STATUS_TM_HEARING),
        (3, date(2025, 10, 25), STATUS_TM_WRITTEN_RESPONSE_TO_HEARING),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_WRITTEN_RESPONSE_TO_HEARING,
        today=date(2025, 11, 1),
    )
    assert not any(r.kind == "hearing" for r in tl.upcoming_reminders)
    assert not any(r.kind == "hearing_response" for r in tl.upcoming_reminders)


def test_registration_certificate_due_fires_when_registered_date_missing():
    accepted = date(2025, 6, 1)
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, accepted, STATUS_TM_ACCEPTED_ADVERTISED),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_ACCEPTED_ADVERTISED,
        today=date(2025, 7, 1),
        registered_note=None,
    )
    assert tl.registration_certificate_due == add_months(accepted, 3)
    assert any(r.kind == "registration_certificate_due" for r in tl.upcoming_reminders)


def test_registration_certificate_due_still_fires_when_registered_date_present_but_note_blank():
    accepted = date(2025, 6, 1)
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, accepted, STATUS_TM_ACCEPTED_ADVERTISED),
        (3, date(2025, 7, 1), STATUS_TM_REGISTERED),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_REGISTERED,
        today=date(2025, 8, 1),
        registered_note=None,
    )
    assert any(r.kind == "registration_certificate_due" for r in tl.upcoming_reminders)


def test_registration_certificate_due_still_fires_when_note_present_but_date_missing():
    accepted = date(2025, 6, 1)
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, accepted, STATUS_TM_ACCEPTED_ADVERTISED),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_ACCEPTED_ADVERTISED,
        today=date(2025, 8, 1),
        registered_note="J-12345",
    )
    assert any(r.kind == "registration_certificate_due" for r in tl.upcoming_reminders)


def test_registration_certificate_due_clears_once_date_and_note_both_present():
    accepted = date(2025, 6, 1)
    states = [
        (1, date(2025, 1, 1), STATUS_TM_APPLICATION_FILED),
        (2, accepted, STATUS_TM_ACCEPTED_ADVERTISED),
        (3, date(2025, 7, 1), STATUS_TM_REGISTERED),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_REGISTERED,
        today=date(2025, 8, 1),
        registered_note="J-12345",
    )
    assert not any(r.kind == "registration_certificate_due" for r in tl.upcoming_reminders)


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


def test_no_renewal_reminder_after_trademark_renewed():
    filing = date(2015, 6, 10)
    states = [
        (1, filing, STATUS_TM_APPLICATION_FILED),
        (2, date(2016, 1, 1), STATUS_TM_REGISTERED),
        (3, date(2025, 7, 1), STATUS_TM_RENEWED),
    ]
    tl = build_timeline_for_tm_application(
        states_ordered=states,
        current_status_name=STATUS_TM_RENEWED,
        today=date(2026, 1, 1),
    )
    assert not any(r.kind == "renewal" for r in tl.upcoming_reminders)


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
