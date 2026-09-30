from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.patents.patent_status_catalog import STATUS_ID_APPLICATION_FILED, STATUS_ID_GRANTED
from app.patents.schemas import (
    PatentApplicantInput,
    PatentInventorInput,
    PatentProjectCreate,
    PatentProjectDetailUpdate,
    PatentProjectUpdate,
    PatentTimelineStatusUpdate,
)
from app.patents.service import create_project, get_project, update_project, update_project_detail, update_status_event


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _create_final_docket(session: Session, docket_no: str) -> dict:
    return create_project(
        session,
        PatentProjectCreate(
            project_mode="final",
            application_type="Non-Provisional Application",
            docket_no=docket_no,
            in_application_no="202312000001",
            in_application_date=date(2023, 1, 1),
            applicant_name="",
            applicants=[PatentApplicantInput(name="Acme Corp", country="IN", address="Somewhere")],
            inventors=[PatentInventorInput(name="Jane Doe", nationality="IN", address="Elsewhere")],
            priorities=[],
        ),
    )


def _update_payload(docket_no: str, grant_number: str | None = None) -> PatentProjectUpdate:
    return PatentProjectUpdate(
        docket_no=docket_no,
        applicant_name="Acme Corp",
        applicant_country="IN",
        applicant_address="Somewhere",
        grant_number=grant_number,
    )


def test_grant_date_without_grant_number_is_rejected_via_detail_update() -> None:
    with _make_session() as session:
        created = _create_final_docket(session, "GRANT-DOCKET-1")

        with pytest.raises(ValueError, match="Grant number is required"):
            update_project_detail(
                session,
                created["id"],
                PatentProjectDetailUpdate(
                    application=_update_payload("GRANT-DOCKET-1"),
                    timeline_updates=[
                        PatentTimelineStatusUpdate(status_id=STATUS_ID_APPLICATION_FILED, status_date=date(2023, 1, 1)),
                        PatentTimelineStatusUpdate(status_id=STATUS_ID_GRANTED, status_date=date(2026, 1, 1)),
                    ],
                ),
            )


def test_grant_date_with_grant_number_in_same_request_succeeds() -> None:
    with _make_session() as session:
        created = _create_final_docket(session, "GRANT-DOCKET-2")

        updated = update_project_detail(
            session,
            created["id"],
            PatentProjectDetailUpdate(
                application=_update_payload("GRANT-DOCKET-2", grant_number="123456"),
                timeline_updates=[
                    PatentTimelineStatusUpdate(status_id=STATUS_ID_APPLICATION_FILED, status_date=date(2023, 1, 1)),
                    PatentTimelineStatusUpdate(status_id=STATUS_ID_GRANTED, status_date=date(2026, 1, 1)),
                ],
            ),
        )

        assert updated is not None
        assert updated["grant_number"] == "123456"
        granted_events = [e for e in updated["status_events"] if e["status_id"] == STATUS_ID_GRANTED]
        assert len(granted_events) == 1
        assert str(granted_events[0]["status_date"]) == "2026-01-01"


def test_grant_date_without_grant_number_is_rejected_via_status_event() -> None:
    with _make_session() as session:
        created = _create_final_docket(session, "GRANT-DOCKET-3")

        with pytest.raises(ValueError, match="Grant number is required"):
            update_status_event(session, created["id"], STATUS_ID_GRANTED, date(2026, 1, 1))


def test_grant_date_via_status_event_succeeds_once_grant_number_already_set() -> None:
    with _make_session() as session:
        created = _create_final_docket(session, "GRANT-DOCKET-4")

        update_project(session, created["id"], _update_payload("GRANT-DOCKET-4", grant_number="789"))

        updated = update_status_event(session, created["id"], STATUS_ID_GRANTED, date(2026, 1, 1))
        assert updated is not None
        assert updated["grant_number"] == "789"
        granted_events = [e for e in updated["status_events"] if e["status_id"] == STATUS_ID_GRANTED]
        assert len(granted_events) == 1


def test_grant_number_and_annuity_fields_persist_and_are_readable() -> None:
    with _make_session() as session:
        created = _create_final_docket(session, "GRANT-DOCKET-5")

        payload = _update_payload("GRANT-DOCKET-5", grant_number="555")
        payload.annuity_paid_upto = date(2025, 6, 1)
        payload.next_annuity_due = date(2026, 6, 1)
        update_project(session, created["id"], payload)

        fetched = get_project(session, created["id"])
        assert fetched is not None
        assert fetched["grant_number"] == "555"
        assert fetched["annuity_paid_upto"] == date(2025, 6, 1)
        assert fetched["next_annuity_due"] == date(2026, 6, 1)
