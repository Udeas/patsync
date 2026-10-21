"""Design project_code is system-generated (DES0001, DES0002, ...), never client-supplied."""

from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from app.models.applications import Status
from app.schemas.applications import ApplicationCreate
from app.services.application_service import create_application
from app.status_catalog import STATUS_ID_APPLICATION_FILED


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(Status(id=STATUS_ID_APPLICATION_FILED, status="Application Filed"))
    session.commit()
    return session


def _create(session: Session, application_number: str):
    return create_application(
        session,
        ApplicationCreate(
            application_number=application_number,
            application_date=date(2025, 1, 10),
            applicant_name="Client",
            applicant_address="Address",
            application_title="Chair",
        ),
    )


def test_first_project_gets_des0001() -> None:
    with _make_session() as session:
        created = _create(session, "100001-001")
        assert created.project_code == "DES0001"


def test_project_codes_increment_sequentially() -> None:
    with _make_session() as session:
        first = _create(session, "100001-001")
        second = _create(session, "100002-001")
        third = _create(session, "100003-001")
        assert [first.project_code, second.project_code, third.project_code] == [
            "DES0001",
            "DES0002",
            "DES0003",
        ]


def test_schema_has_no_project_code_field() -> None:
    # project_code is server-generated only; the create schema must not expose
    # it as a settable field, so a client-supplied value can never take effect.
    assert "project_code" not in ApplicationCreate.model_fields
