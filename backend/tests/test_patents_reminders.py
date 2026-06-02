from datetime import date

from app.patents.patent_status_catalog import (
    STATUS_ID_APPLICATION_FILED,
    STATUS_ID_FER_ISSUED,
    STATUS_ID_FER_RESPONSE_SUBMITTED,
    STATUS_ID_GRANTED,
    STATUS_ID_HEARING,
    STATUS_ID_NON_PROVISIONAL_APPLICATION,
    STATUS_ID_PUBLICATION,
    STATUS_ID_REQUEST_FOR_EXAMINATION,
)
from app.patents.reminders import compute_next_patent_action
from app.patents.workflow import compute_rfe_deadline


def test_rfe_due_when_filed_without_rfe():
    in_date = date(2026, 1, 1)
    action = compute_next_patent_action(
        filled={STATUS_ID_APPLICATION_FILED: in_date},
        current_status_id=STATUS_ID_APPLICATION_FILED,
        in_application_date=in_date,
    )
    assert action is not None
    assert action.message == "Request for Examination"
    assert action.due_date == compute_rfe_deadline(in_date)


def test_rfe_due_uses_earliest_priority_anchor():
    in_date = date(2026, 1, 1)
    priority = date(2024, 6, 1)
    action = compute_next_patent_action(
        filled={STATUS_ID_APPLICATION_FILED: in_date},
        current_status_id=STATUS_ID_APPLICATION_FILED,
        in_application_date=in_date,
        priority_dates=[priority],
    )
    assert action is not None
    assert action.due_date == compute_rfe_deadline(in_date, [priority])


def test_publication_current_still_shows_rfe_deadline():
    in_date = date(2026, 1, 1)
    action = compute_next_patent_action(
        filled={
            STATUS_ID_APPLICATION_FILED: in_date,
            STATUS_ID_PUBLICATION: date(2026, 3, 1),
        },
        current_status_id=STATUS_ID_PUBLICATION,
        in_application_date=in_date,
    )
    assert action is not None
    assert action.message == "Request for Examination"


def test_fer_issued_current_shows_fer_response_due():
    fer_date = date(2026, 1, 10)
    action = compute_next_patent_action(
        filled={
            STATUS_ID_APPLICATION_FILED: date(2026, 1, 1),
            STATUS_ID_REQUEST_FOR_EXAMINATION: date(2026, 2, 1),
            STATUS_ID_FER_ISSUED: fer_date,
        },
        current_status_id=STATUS_ID_FER_ISSUED,
        in_application_date=date(2026, 1, 1),
    )
    assert action is not None
    assert action.message == "FER Response"
    assert action.due_date == date(2026, 7, 10)


def test_hearing_current_uses_exact_hearing_date():
    hearing_date = date(2026, 6, 28)
    action = compute_next_patent_action(
        filled={
            STATUS_ID_APPLICATION_FILED: date(2026, 1, 1),
            STATUS_ID_REQUEST_FOR_EXAMINATION: date(2026, 2, 1),
            STATUS_ID_FER_ISSUED: date(2026, 3, 1),
            STATUS_ID_FER_RESPONSE_SUBMITTED: date(2026, 4, 1),
            STATUS_ID_HEARING: hearing_date,
        },
        current_status_id=STATUS_ID_HEARING,
        in_application_date=date(2026, 1, 1),
    )
    assert action is not None
    assert action.message == "Hearing"
    assert action.due_date == hearing_date


def test_rfe_current_has_no_due_action():
    action = compute_next_patent_action(
        filled={
            STATUS_ID_APPLICATION_FILED: date(2026, 1, 1),
            STATUS_ID_REQUEST_FOR_EXAMINATION: date(2026, 2, 1),
        },
        current_status_id=STATUS_ID_REQUEST_FOR_EXAMINATION,
        in_application_date=date(2026, 1, 1),
    )
    assert action is None


def test_fer_response_current_without_hearing_has_no_due():
    action = compute_next_patent_action(
        filled={
            STATUS_ID_APPLICATION_FILED: date(2026, 1, 1),
            STATUS_ID_REQUEST_FOR_EXAMINATION: date(2026, 2, 1),
            STATUS_ID_FER_ISSUED: date(2026, 3, 1),
            STATUS_ID_FER_RESPONSE_SUBMITTED: date(2026, 4, 1),
        },
        current_status_id=STATUS_ID_FER_RESPONSE_SUBMITTED,
        in_application_date=date(2026, 1, 1),
    )
    assert action is None


def test_granted_current_has_no_due():
    action = compute_next_patent_action(
        filled={
            STATUS_ID_APPLICATION_FILED: date(2026, 1, 1),
            STATUS_ID_GRANTED: date(2026, 5, 1),
        },
        current_status_id=STATUS_ID_GRANTED,
        in_application_date=date(2026, 1, 1),
    )
    assert action is None


def test_fer_response_current_suppresses_stale_fer_reminder():
    action = compute_next_patent_action(
        filled={
            STATUS_ID_APPLICATION_FILED: date(2026, 1, 1),
            STATUS_ID_REQUEST_FOR_EXAMINATION: date(2026, 2, 1),
            STATUS_ID_FER_ISSUED: date(2026, 3, 1),
            STATUS_ID_FER_RESPONSE_SUBMITTED: date(2026, 4, 1),
        },
        current_status_id=STATUS_ID_FER_RESPONSE_SUBMITTED,
        in_application_date=date(2026, 1, 1),
    )
    assert action is None


def test_provisional_due_shows_non_provisional_in_12_months():
    in_date = date(2026, 1, 15)
    action = compute_next_patent_action(
        filled={STATUS_ID_APPLICATION_FILED: in_date},
        current_status_id=STATUS_ID_APPLICATION_FILED,
        in_application_date=in_date,
        provisional_kind="OP",
    )
    assert action is not None
    assert action.message == "Non-Provisional Application"
    assert action.due_date == date(2027, 1, 15)


def test_provisional_after_non_provisional_uses_existing_rfe_flow():
    in_date = date(2026, 1, 15)
    non_provisional_date = date(2026, 12, 1)
    action = compute_next_patent_action(
        filled={
            STATUS_ID_APPLICATION_FILED: in_date,
            STATUS_ID_NON_PROVISIONAL_APPLICATION: non_provisional_date,
        },
        current_status_id=STATUS_ID_NON_PROVISIONAL_APPLICATION,
        in_application_date=in_date,
        provisional_kind="OP",
    )
    assert action is not None
    assert action.message == "Request for Examination"
    assert action.due_date == compute_rfe_deadline(non_provisional_date)

