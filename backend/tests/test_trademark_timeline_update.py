"""Trademark project detail timeline updates must not delete omitted statuses."""

from datetime import date, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.trademark import TmApplicationData, TmApplicationState, TmStatus
from app.schemas.trademark import (
    TmApplicationCreate,
    TmApplicationUpdate,
    TmProjectDetailUpdate,
    TmTimelineStatusUpdate,
)
from app.services import trademark_service as svc
from app.tm_status_catalog import STATUS_ID_TM_APPLICATION_FILED, TM_STATUS_SEED


@pytest.fixture
def tm_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        for sid, label in TM_STATUS_SEED:
            s.add(TmStatus(id=sid, status=label))
        s.commit()
    with Session(engine) as session:
        yield session


def test_partial_timeline_update_preserves_other_statuses(tm_session: Session):
    created = svc.create_tm_application(
        tm_session,
        TmApplicationCreate(
            application_number="1234567",
            application_date=date(2025, 1, 10),
            applicant_name="Client",
            applicant_type="Individual",
            tm_name="Mark",
            tm_type="Wordmark",
            tm_class="5",
            applicant_address="Address",
        ),
    )
    app_row = tm_session.get(TmApplicationData, created.id)
    assert app_row is not None
    now = datetime.utcnow()
    for status_id, milestone_date in (
        (2, date(2025, 1, 20)),
        (3, date(2025, 2, 1)),
        (4, date(2025, 3, 1)),
    ):
        tm_session.add(
            TmApplicationState(
                application_num=app_row.application_num,
                status_id=status_id,
                application_date=milestone_date,
                created_date=now,
                modified_date=now,
            )
        )
    tm_session.commit()

    before = tm_session.exec(select(TmApplicationState)).all()
    status_ids_before = {s.status_id for s in before}

    svc.update_tm_project_detail(
        tm_session,
        created.id,
        TmProjectDetailUpdate(
            application=TmApplicationUpdate(applicant_name="Client Updated"),
            timeline_updates=[
                TmTimelineStatusUpdate(
                    status_id=STATUS_ID_TM_APPLICATION_FILED,
                    application_date=date(2025, 1, 15),
                )
            ],
        ),
    )

    after = tm_session.exec(select(TmApplicationState)).all()
    status_ids_after = {s.status_id for s in after}
    assert STATUS_ID_TM_APPLICATION_FILED in status_ids_after
    assert 4 in status_ids_after, "FER Issued status must remain after partial timeline update"
    assert status_ids_before - status_ids_after == set()
