"""Trademark project_code is system-generated (TM0001, TM0002, ...), never client-supplied."""

from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from app.models.trademark import TmStatus
from app.schemas.trademark import TmApplicationCreate
from app.services.trademark_service import create_tm_application
from app.tm_status_catalog import STATUS_ID_TM_APPLICATION_FILED


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(TmStatus(id=STATUS_ID_TM_APPLICATION_FILED, status="Application filed"))
    session.commit()
    return session


def _create(session: Session, application_number: str):
    return create_tm_application(
        session,
        TmApplicationCreate(
            application_number=application_number,
            application_date=date(2025, 1, 10),
            applicant_name="Client",
            applicant_type="Individual",
            tm_name="Mark",
            tm_type="Wordmark",
            tm_class="5",
            tm_usage_status="Proposed to be used",
            applicant_address="Address",
        ),
    )


def test_first_project_gets_tm0001() -> None:
    with _make_session() as session:
        created = _create(session, "1000001")
        assert created.project_code == "TM0001"


def test_project_codes_increment_sequentially() -> None:
    with _make_session() as session:
        first = _create(session, "1000001")
        second = _create(session, "1000002")
        third = _create(session, "1000003")
        assert [first.project_code, second.project_code, third.project_code] == [
            "TM0001",
            "TM0002",
            "TM0003",
        ]


def test_schema_has_no_project_code_field() -> None:
    # project_code is server-generated only; the create schema must not expose
    # it as a settable field, so a client-supplied value can never take effect.
    assert "project_code" not in TmApplicationCreate.model_fields
