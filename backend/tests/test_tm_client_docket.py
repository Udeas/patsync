from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from app.models.trademark import TmStatus
from app.schemas.trademark import TmApplicationCreate, TmApplicationUpdate
from app.services.trademark_service import (
    create_tm_application,
    get_tm_application_by_id,
    update_tm_application,
)
from app.tm_status_catalog import STATUS_ID_TM_APPLICATION_FILED


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(TmStatus(id=STATUS_ID_TM_APPLICATION_FILED, status="Application filed"))
    session.commit()
    return session


def test_create_and_update_persists_tm_client_docket_no() -> None:
    with _make_session() as session:
        created = create_tm_application(
            session,
            TmApplicationCreate(
                application_number="1234567",
                application_date=date(2024, 1, 1),
                applicant_name="Acme",
                applicant_type="Company",
                tm_name="AcmeMark",
                tm_type="Wordmark",
                tm_class="9",
                applicant_address="Somewhere",
                client_docket_no="TM-DOCKET-1",
            ),
        )
        assert created.client_docket_no == "TM-DOCKET-1"

        reloaded = get_tm_application_by_id(session, created.id)
        assert reloaded is not None
        assert reloaded.client_docket_no == "TM-DOCKET-1"

        updated = update_tm_application(
            session, created.id, TmApplicationUpdate(client_docket_no="TM-DOCKET-2")
        )
        assert updated is not None
        assert updated.client_docket_no == "TM-DOCKET-2"
