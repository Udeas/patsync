from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from app.models.applications import Status
from app.schemas.applications import ApplicationCreate, ApplicationUpdate
from app.services.application_service import (
    create_application,
    get_application_by_id,
    update_application,
)
from app.status_catalog import STATUS_ID_APPLICATION_FILED


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(Status(id=STATUS_ID_APPLICATION_FILED, status="Application Filed"))
    session.commit()
    return session


def test_create_and_update_persists_client_docket_no() -> None:
    with _make_session() as session:
        created = create_application(
            session,
            ApplicationCreate(
                project_code="DSGN1",
                application_number="123456-001",
                application_date=date(2024, 1, 1),
                applicant_name="Acme",
                applicant_address="Somewhere",
                application_title="Chair",
                client_docket_no="CL-DOCKET-1",
            ),
        )
        assert created.client_docket_no == "CL-DOCKET-1"

        reloaded = get_application_by_id(session, created.id)
        assert reloaded is not None
        assert reloaded.client_docket_no == "CL-DOCKET-1"

        updated = update_application(
            session, created.id, ApplicationUpdate(client_docket_no="CL-DOCKET-2")
        )
        assert updated is not None
        assert updated.client_docket_no == "CL-DOCKET-2"
