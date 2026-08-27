"""End-to-end annuity workflow through the service layer - the E17-06IN
worked example, and each numbered test scenario from the spec.
"""

from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.patents.patent_status_catalog import STATUS_ID_APPLICATION_FILED, STATUS_ID_GRANTED
from app.patents.schemas import (
    PatentAnnuityPaymentInput,
    PatentAnnuityTransferInput,
    PatentApplicantInput,
    PatentInventorInput,
    PatentProjectCreate,
    PatentProjectUpdate,
)
from app.patents.service import (
    create_project,
    get_annuity_summary,
    get_project,
    record_annuity_payment,
    transfer_annuity_case,
    update_project,
    update_status_event,
)

FILING_DATE = date(2020, 12, 24)
GRANT_DATE = date(2026, 8, 13)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _create_e17_06in(session: Session) -> dict:
    return create_project(
        session,
        PatentProjectCreate(
            project_mode="final",
            application_type="Convention",
            docket_no="E17-06IN",
            in_application_no="202014056469",
            in_application_date=FILING_DATE,
            applicant_name="",
            applicants=[PatentApplicantInput(name="TMRW Foundation IP SARL", country="LU", address="Somewhere")],
            inventors=[PatentInventorInput(name="Vinay Sharma", nationality="IN", address="Elsewhere")],
            priorities=[
                {
                    "priority_application_no": "PROV-1",
                    "priority_application_date": date(2019, 12, 30),
                    "country": "US",
                    "title": "Multi-dimensional review system",
                }
            ],
        ),
    )


def _grant(session: Session, project_id: int, grant_date: date = GRANT_DATE) -> None:
    # PatentProjectUpdate overwrites in_application_no/date unconditionally
    # (unlike grant_number et al, which are only-if-not-None) - echo the
    # existing values back, matching how the frontend always does on this
    # endpoint for fields it isn't editing.
    update_project(
        session,
        project_id,
        PatentProjectUpdate(
            docket_no="E17-06IN",
            applicant_name="TMRW Foundation IP SARL",
            in_application_no="202014056469",
            in_application_date=FILING_DATE,
            grant_number="599090",
        ),
    )
    update_status_event(session, project_id, STATUS_ID_GRANTED, grant_date)


# --- Test 1: E17-06IN accumulated years, deadline, fee, schedule -----------


def test_1_e17_06in_accumulated_years_deadline_and_fee():
    with _make_session() as session:
        project = _create_e17_06in(session)
        update_status_event(session, project["id"], STATUS_ID_APPLICATION_FILED, FILING_DATE)
        _grant(session, project["id"])

        summary = get_annuity_summary(session, project["id"])
        assert summary is not None
        assert summary.filing_date == FILING_DATE
        assert summary.grant_date == GRANT_DATE
        assert summary.accumulated_unpaid_years == [3, 4, 5, 6, 7]
        assert summary.is_post_grant_deadline_pending is True
        assert summary.next_due_date == date(2026, 11, 13)  # grant + 3 months
        assert summary.next_due_year == 3

        # renewal schedule continues from filing date, dynamically computed
        schedule_by_year = {row.year: row for row in summary.schedule}
        assert schedule_by_year[3].due_date == date(2022, 12, 24)
        assert schedule_by_year[7].due_date == date(2026, 12, 24)
        assert schedule_by_year[20].due_date == date(2039, 12, 24)
        assert schedule_by_year[3].fee == 4_000
        assert schedule_by_year[7].fee == 12_000


# --- Test 2: pay 3rd-7th year -----------------------------------------------


def test_2_pay_3rd_to_7th_year():
    with _make_session() as session:
        project = _create_e17_06in(session)
        _grant(session, project["id"])

        summary = record_annuity_payment(
            session,
            project["id"],
            PatentAnnuityPaymentInput(payment_date=date(2026, 11, 13), years=[3, 4, 5, 6, 7]),
        )
        assert summary is not None
        assert summary.payments[0].total_fee == 28_000
        assert summary.paid_till_date == date(2027, 12, 24)
        assert summary.next_due_year == 8


# --- Test 3: pay 8th-10th year afterward -----------------------------------


def test_3_pay_8th_to_10th_year_after_3rd_to_7th():
    with _make_session() as session:
        project = _create_e17_06in(session)
        _grant(session, project["id"])
        record_annuity_payment(
            session, project["id"], PatentAnnuityPaymentInput(payment_date=date(2026, 11, 13), years=[3, 4, 5, 6, 7])
        )

        summary = record_annuity_payment(
            session, project["id"], PatentAnnuityPaymentInput(payment_date=date(2028, 1, 5), years=[8, 9, 10])
        )
        assert summary is not None
        assert len(summary.payments) == 2
        assert summary.payments[1].total_fee == 36_000
        assert summary.paid_till_date == date(2030, 12, 24)
        assert summary.next_due_year == 11


# --- Test 4: duplicate year rejected ---------------------------------------


def test_4_duplicate_year_cannot_be_paid_again():
    with _make_session() as session:
        project = _create_e17_06in(session)
        _grant(session, project["id"])
        record_annuity_payment(
            session, project["id"], PatentAnnuityPaymentInput(payment_date=date(2026, 11, 13), years=[3, 4, 5, 6, 7])
        )

        with pytest.raises(ValueError, match="already paid"):
            record_annuity_payment(
                session, project["id"], PatentAnnuityPaymentInput(payment_date=date(2026, 12, 1), years=[7, 8])
            )


# --- Test 5: advance payment of future years -------------------------------


def test_5_advance_payment_skips_paid_years_in_next_reminder():
    with _make_session() as session:
        project = _create_e17_06in(session)
        _grant(session, project["id"])

        summary = record_annuity_payment(
            session,
            project["id"],
            PatentAnnuityPaymentInput(payment_date=date(2026, 11, 13), years=[3, 4, 5, 6, 7, 8, 9]),
        )
        assert summary is not None
        assert summary.payments[0].total_fee == 4_000 * 4 + 12_000 * 3
        assert summary.paid_till_date == date(2029, 12, 24)
        assert summary.next_due_year == 10


# --- Test 6: grant-date change before payment recalculates -----------------


def test_6_grant_date_change_before_payment_recalculates_deadline_and_batch():
    with _make_session() as session:
        project = _create_e17_06in(session)
        _grant(session, project["id"], grant_date=date(2026, 8, 13))

        summary_before = get_annuity_summary(session, project["id"])
        assert summary_before.accumulated_unpaid_years == [3, 4, 5, 6, 7]
        assert summary_before.next_due_date == date(2026, 11, 13)

        # Grant date corrected to a year earlier - fewer years accumulated,
        # deadline shifts with it.
        update_status_event(session, project["id"], STATUS_ID_GRANTED, date(2025, 8, 13))

        summary_after = get_annuity_summary(session, project["id"])
        assert summary_after.grant_date == date(2025, 8, 13)
        assert summary_after.accumulated_unpaid_years == [3, 4, 5, 6]
        assert summary_after.next_due_date == date(2025, 11, 13)


# --- Test 7: historical payment protected across grant-date change --------


def test_7_grant_date_change_after_payment_preserves_payment_history():
    with _make_session() as session:
        project = _create_e17_06in(session)
        _grant(session, project["id"])
        record_annuity_payment(
            session, project["id"], PatentAnnuityPaymentInput(payment_date=date(2026, 11, 13), years=[3, 4, 5, 6, 7])
        )

        # Grant date edited after payment already recorded.
        update_status_event(session, project["id"], STATUS_ID_GRANTED, date(2026, 9, 1))

        summary = get_annuity_summary(session, project["id"])
        assert summary is not None
        assert len(summary.payments) == 1
        assert summary.payments[0].payment_date == date(2026, 11, 13)
        assert summary.payments[0].total_fee == 28_000
        assert summary.payments[0].years == [3, 4, 5, 6, 7]
        assert summary.paid_till_date == date(2027, 12, 24)


# --- Transfer: locks the case, no further reminders/payments ---------------


def test_transfer_marks_case_locked_and_clears_next_due():
    with _make_session() as session:
        project = _create_e17_06in(session)
        _grant(session, project["id"])

        before = get_annuity_summary(session, project["id"])
        assert before.is_transferred is False
        assert before.accumulated_unpaid_years == [3, 4, 5, 6, 7]
        assert before.next_due_date is not None

        summary = transfer_annuity_case(
            session, project["id"], PatentAnnuityTransferInput(comment="Client moved to another firm")
        )
        assert summary is not None
        assert summary.is_transferred is True
        assert summary.transferred_comment == "Client moved to another firm"
        assert summary.transferred_at is not None
        assert summary.next_due_year is None
        assert summary.next_due_date is None
        assert summary.is_post_grant_deadline_pending is False
        assert summary.accumulated_unpaid_years == []


def test_transfer_suppresses_due_action_on_the_project_response():
    with _make_session() as session:
        project = _create_e17_06in(session)
        _grant(session, project["id"])
        transfer_annuity_case(session, project["id"], PatentAnnuityTransferInput(comment="Transferred"))

        row = get_project(session, project["id"])
        assert row is not None
        assert row["due_action"] is None
        assert row["action_due_date"] is None


def test_transfer_requires_a_comment():
    with _make_session() as session:
        project = _create_e17_06in(session)
        _grant(session, project["id"])
        with pytest.raises(ValueError):
            transfer_annuity_case(session, project["id"], PatentAnnuityTransferInput(comment="   "))


def test_transfer_cannot_be_done_twice():
    with _make_session() as session:
        project = _create_e17_06in(session)
        _grant(session, project["id"])
        transfer_annuity_case(session, project["id"], PatentAnnuityTransferInput(comment="First"))
        with pytest.raises(ValueError, match="already"):
            transfer_annuity_case(session, project["id"], PatentAnnuityTransferInput(comment="Second"))


def test_payment_rejected_after_transfer():
    with _make_session() as session:
        project = _create_e17_06in(session)
        _grant(session, project["id"])
        transfer_annuity_case(session, project["id"], PatentAnnuityTransferInput(comment="Transferred"))

        with pytest.raises(ValueError, match="transferred"):
            record_annuity_payment(
                session, project["id"], PatentAnnuityPaymentInput(payment_date=date(2026, 11, 13), years=[3])
            )


def test_transfer_preserves_existing_payment_history():
    with _make_session() as session:
        project = _create_e17_06in(session)
        _grant(session, project["id"])
        record_annuity_payment(
            session, project["id"], PatentAnnuityPaymentInput(payment_date=date(2026, 11, 13), years=[3, 4, 5, 6, 7])
        )

        summary = transfer_annuity_case(session, project["id"], PatentAnnuityTransferInput(comment="Transferred"))
        assert summary is not None
        assert len(summary.payments) == 1
        assert summary.payments[0].total_fee == 28_000
        assert summary.paid_till_date == date(2027, 12, 24)
