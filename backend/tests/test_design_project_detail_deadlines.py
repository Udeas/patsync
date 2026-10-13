"""get_project_detail() must thread through the deadline/reminder fields that
get_application_by_id already computes - previously dropped when building
ProjectDetailRead, so the Design project view had no Next Due Action data."""

from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from app.models.applications import Status
from app.schemas.applications import ApplicationCreate, ApplicationStatusUpdate
from app.services.application_service import create_application, get_project_detail, update_application_status
from app.status_catalog import STATUS_FER_ISSUED, STATUS_ID_APPLICATION_FILED

STATUS_ID_FER_ISSUED = 3


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(Status(id=STATUS_ID_APPLICATION_FILED, status="Application Filed"))
    session.add(Status(id=STATUS_ID_FER_ISSUED, status=STATUS_FER_ISSUED))
    session.commit()
    return session


def _create_application(session: Session):
    return create_application(
        session,
        ApplicationCreate(
            application_number="100001-001",
            application_date=date(2025, 1, 10),
            applicant_name="Client",
            applicant_address="Address",
            application_title="Chair",
        ),
    )


def test_project_detail_includes_fer_response_deadline_after_fer_issued() -> None:
    with _make_session() as session:
        created = _create_application(session)
        update_application_status(
            session,
            created.id,
            ApplicationStatusUpdate(status_id=STATUS_ID_FER_ISSUED, application_date=date(2026, 1, 10)),
        )
        detail = get_project_detail(session, created.id)
        assert detail.fer_response_deadline is not None


def test_project_detail_upcoming_reminders_defaults_to_empty_list() -> None:
    with _make_session() as session:
        created = _create_application(session)
        detail = get_project_detail(session, created.id)
        assert detail.upcoming_reminders == []
