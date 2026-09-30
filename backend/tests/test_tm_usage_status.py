"""TM usage details: 'Proposed to be used' vs 'Used since <date>'."""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine

from app.models.trademark import TmStatus
from app.schemas.trademark import TmApplicationCreate, TmApplicationUpdate
from app.services.trademark_service import create_tm_application, update_tm_application
from app.tm_status_catalog import STATUS_ID_TM_APPLICATION_FILED


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(TmStatus(id=STATUS_ID_TM_APPLICATION_FILED, status="Application filed"))
    session.commit()
    return session


def _base_kwargs(**overrides):
    kwargs = dict(
        application_number="1234567",
        application_date=date(2025, 1, 10),
        applicant_name="Client",
        applicant_type="Individual",
        tm_name="Mark",
        tm_type="Wordmark",
        tm_class="5",
        applicant_address="Address",
    )
    kwargs.update(overrides)
    return kwargs


def test_proposed_to_be_used_stores_no_date() -> None:
    with _make_session() as session:
        created = create_tm_application(
            session, TmApplicationCreate(**_base_kwargs(tm_usage_status="Proposed to be used"))
        )
        assert created.tm_usage_status == "Proposed to be used"
        assert created.tm_used_since_date is None


def test_used_since_stores_the_given_date() -> None:
    with _make_session() as session:
        created = create_tm_application(
            session,
            TmApplicationCreate(
                **_base_kwargs(tm_usage_status="Used since", tm_used_since_date=date(2020, 6, 15))
            ),
        )
        assert created.tm_usage_status == "Used since"
        assert created.tm_used_since_date == date(2020, 6, 15)


def test_used_since_requires_a_date() -> None:
    with pytest.raises(ValidationError):
        TmApplicationCreate(**_base_kwargs(tm_usage_status="Used since"))


def test_used_since_rejects_a_future_date() -> None:
    with pytest.raises(ValidationError):
        TmApplicationCreate(
            **_base_kwargs(
                tm_usage_status="Used since",
                tm_used_since_date=date.today() + timedelta(days=1),
            )
        )


def test_proposed_to_be_used_rejects_a_stray_date() -> None:
    with pytest.raises(ValidationError):
        TmApplicationCreate(
            **_base_kwargs(tm_usage_status="Proposed to be used", tm_used_since_date=date(2020, 1, 1))
        )


def test_invalid_usage_status_value_rejected() -> None:
    with pytest.raises(ValidationError):
        TmApplicationCreate(**_base_kwargs(tm_usage_status="Something else"))


def test_update_can_switch_from_proposed_to_used_since() -> None:
    with _make_session() as session:
        created = create_tm_application(
            session, TmApplicationCreate(**_base_kwargs(tm_usage_status="Proposed to be used"))
        )
        updated = update_tm_application(
            session,
            created.id,
            TmApplicationUpdate(tm_usage_status="Used since", tm_used_since_date=date(2019, 3, 1)),
        )
        assert updated is not None
        assert updated.tm_usage_status == "Used since"
        assert updated.tm_used_since_date == date(2019, 3, 1)


def test_update_can_switch_back_to_proposed_and_clear_the_date() -> None:
    with _make_session() as session:
        created = create_tm_application(
            session,
            TmApplicationCreate(
                **_base_kwargs(tm_usage_status="Used since", tm_used_since_date=date(2019, 3, 1))
            ),
        )
        updated = update_tm_application(
            session,
            created.id,
            TmApplicationUpdate(tm_usage_status="Proposed to be used", tm_used_since_date=None),
        )
        assert updated is not None
        assert updated.tm_usage_status == "Proposed to be used"
        assert updated.tm_used_since_date is None


def test_update_ignoring_usage_status_entirely_is_not_blocked_by_its_validator() -> None:
    with _make_session() as session:
        created = create_tm_application(
            session, TmApplicationCreate(**_base_kwargs(tm_usage_status="Proposed to be used"))
        )
        updated = update_tm_application(session, created.id, TmApplicationUpdate(applicant_name="New Name"))
        assert updated is not None
        assert updated.applicant_name == "New Name"
        assert updated.tm_usage_status == "Proposed to be used"
