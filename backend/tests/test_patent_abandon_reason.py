from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.patents.patent_status_catalog import STATUS_ID_ABANDONED
from app.patents.schemas import PatentApplicantInput, PatentInventorInput, PatentProjectCreate
from app.patents.service import create_project, update_status_event


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _final_project(session: Session) -> dict:
    return create_project(
        session,
        PatentProjectCreate(
            project_mode="final",
            application_type="Ordinary Application",
            docket_no="ABND-1",
            in_application_no="202411012345",
            in_application_date=date(2024, 11, 1),
            applicant_name="Acme",
            applicant_country="IN",
            applicant_address="Addr",
            applicants=[PatentApplicantInput(name="Acme", country="IN", address="Addr")],
            inventors=[PatentInventorInput(name="Inv A", nationality="IN", address="Inv Addr")],
            priorities=[],
            international_applications=[],
        ),
    )


def test_abandon_requires_reason() -> None:
    with _make_session() as session:
        project = _final_project(session)
        with pytest.raises(ValueError, match="Abandon reason is required"):
            update_status_event(
                session, project["id"], STATUS_ID_ABANDONED, date(2025, 1, 1), abandon_reason="  "
            )


def test_abandon_persists_reason() -> None:
    with _make_session() as session:
        project = _final_project(session)
        updated = update_status_event(
            session,
            project["id"],
            STATUS_ID_ABANDONED,
            date(2025, 1, 1),
            abandon_reason="Fees not paid",
        )
        assert updated is not None
        assert updated["current_status_id"] == STATUS_ID_ABANDONED
        assert updated["abandon_reason"] == "Fees not paid"
