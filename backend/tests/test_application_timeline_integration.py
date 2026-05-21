"""Service + read model wiring for patent timeline fields."""

from datetime import date
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models.applications import Status
from app.schemas.applications import ApplicationCreate, ApplicationStatusUpdate, ApplicationUpdate
from app.services import application_service as svc
from app.status_catalog import PATENT_STATUS_SEED


@pytest.fixture
def session_fixture():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        for sid, lbl in PATENT_STATUS_SEED:
            s.add(Status(id=sid, status=lbl))
        s.commit()
    with Session(engine) as session:
        yield session


def test_get_applications_surfaces_fer_deadline_and_reminders_when_fer_issued(
    session_fixture: Session,
):
    created = svc.create_application(
        session_fixture,
        ApplicationCreate(
            application_number="100000-001",
            application_date=date(2025, 1, 10),
            applicant_name="A",
            applicant_address="Addr",
            application_title="Title",
        ),
    )
    svc.update_application_status(
        session_fixture,
        created.id,
        ApplicationStatusUpdate(status_id=3, application_date=date(2025, 3, 1)),
    )
    with patch("app.services.application_service.date") as mock_date:
        mock_date.today.return_value = date(2025, 5, 15)
        rows = svc.get_applications(session_fixture)
    assert len(rows) == 1
    assert rows[0].fer_response_deadline is not None
    assert any(r.kind == "fer_deadline" for r in rows[0].upcoming_reminders)


def test_get_application_by_id_uses_latest_state(session_fixture: Session):
    created = svc.create_application(
        session_fixture,
        ApplicationCreate(
            application_number="200000-001",
            application_date=date(2025, 1, 1),
            applicant_name="B",
            applicant_address="Addr",
            application_title="T2",
        ),
    )
    svc.update_application_status(
        session_fixture,
        created.id,
        ApplicationStatusUpdate(status_id=4, application_date=date(2025, 8, 1)),
    )
    read = svc.get_application_by_id(session_fixture, created.id)
    assert read is not None
    assert read.application_current_status == "FER Response submitted"
    assert read.application_date == date(2025, 8, 1)


def test_update_application_allows_edit_project_data(session_fixture: Session):
    created = svc.create_application(
        session_fixture,
        ApplicationCreate(
            application_number="300000-001",
            application_date=date(2025, 2, 1),
            applicant_name="Original Name",
            applicant_address="Original Address",
            application_title="Original Title",
            comments="Original comment",
        ),
    )

    updated = svc.update_application(
        session_fixture,
        created.id,
        ApplicationUpdate(
            application_number="300001-001",
            application_date=date(2025, 2, 10),
            applicant_name="Updated Name",
            applicant_address="Updated Address",
            application_title="Updated Title",
            comments="Updated comment",
        ),
    )

    assert updated is not None
    assert updated.application_number == "300001-001"
    assert updated.application_date == date(2025, 2, 10)
    assert updated.applicant_name == "Updated Name"
    assert updated.applicant_address == "Updated Address"
    assert updated.application_title == "Updated Title"
    assert updated.comments == "Updated comment"
