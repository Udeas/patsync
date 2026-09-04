"""Trademark custom events: create (with/without reminder), close, delete, reminder surfacing."""

from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models.trademark import TmStatus
from app.schemas.trademark import TmApplicationCreate, TmCustomEventClose, TmCustomEventCreate
from app.services.trademark_service import (
    add_tm_custom_event,
    close_tm_custom_event,
    create_tm_application,
    delete_tm_custom_event,
    get_tm_application_by_id,
    get_tm_applications,
    get_tm_project_detail,
)
from app.tm_status_catalog import STATUS_ID_TM_APPLICATION_FILED


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(TmStatus(id=STATUS_ID_TM_APPLICATION_FILED, status="Application filed"))
    session.commit()
    return session


def _create_application(session: Session, application_number: str = "1234567"):
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
            applicant_address="Address",
        ),
    )


def test_no_reminder_event_is_added_without_reminder_date() -> None:
    with _make_session() as session:
        created = _create_application(session)
        events = add_tm_custom_event(
            session,
            created.id,
            TmCustomEventCreate(event_type="Notice u/s 132", event_date=date(2026, 3, 15)),
        )
        assert events is not None
        assert len(events) == 1
        assert events[0].reminder_option == "none"
        assert events[0].reminder_date is None


def test_reminder_date_computed_for_each_option() -> None:
    with _make_session() as session:
        created = _create_application(session)
        for option, expected in [
            ("15d", date(2026, 3, 30)),
            ("1m", date(2026, 4, 15)),
            ("3m", date(2026, 6, 15)),
        ]:
            events = add_tm_custom_event(
                session,
                created.id,
                TmCustomEventCreate(
                    event_type="Notice u/s 132", event_date=date(2026, 3, 15), reminder_option=option
                ),
            )
            match = next(e for e in events if e.reminder_option == option)
            assert match.reminder_date == expected


def test_custom_event_surfaces_in_project_detail_and_reminders() -> None:
    with _make_session() as session:
        created = _create_application(session)
        add_tm_custom_event(
            session,
            created.id,
            TmCustomEventCreate(event_type="Notice u/s 132", event_date=date(2026, 3, 15), reminder_option="15d"),
        )
        detail = get_tm_project_detail(session, created.id)
        assert len(detail.custom_events) == 1
        assert any(r.kind == "custom_event" for r in detail.upcoming_reminders)


def test_closing_event_removes_it_from_reminders_but_keeps_it_in_custom_events() -> None:
    with _make_session() as session:
        created = _create_application(session)
        events = add_tm_custom_event(
            session,
            created.id,
            TmCustomEventCreate(event_type="Notice u/s 132", event_date=date(2026, 3, 15), reminder_option="1m"),
        )
        event_id = events[0].id
        closed = close_tm_custom_event(
            session, created.id, event_id, TmCustomEventClose(closure_date=date(2026, 2, 20))
        )
        assert closed[0].closure_date == date(2026, 2, 20)

        detail = get_tm_project_detail(session, created.id)
        assert len(detail.custom_events) == 1
        assert not any(r.kind == "custom_event" for r in detail.upcoming_reminders)


def test_closing_already_closed_event_raises() -> None:
    with _make_session() as session:
        created = _create_application(session)
        events = add_tm_custom_event(
            session,
            created.id,
            TmCustomEventCreate(event_type="Notice u/s 132", event_date=date(2026, 3, 15), reminder_option="15d"),
        )
        event_id = events[0].id
        close_tm_custom_event(session, created.id, event_id, TmCustomEventClose(closure_date=date(2026, 2, 20)))
        with pytest.raises(ValueError, match="already closed"):
            close_tm_custom_event(session, created.id, event_id, TmCustomEventClose(closure_date=date(2026, 2, 21)))


def test_delete_allowed_only_for_open_no_reminder_events() -> None:
    with _make_session() as session:
        created = _create_application(session)
        no_reminder = add_tm_custom_event(
            session, created.id, TmCustomEventCreate(event_type="Notice u/s 132", event_date=date(2026, 3, 15))
        )
        no_reminder_id = no_reminder[0].id

        with_reminder = add_tm_custom_event(
            session,
            created.id,
            TmCustomEventCreate(event_type="Notice u/s 132", event_date=date(2026, 4, 1), reminder_option="15d"),
        )
        with_reminder_id = next(e.id for e in with_reminder if e.reminder_option == "15d")

        with pytest.raises(ValueError, match="Only open, no-reminder events"):
            delete_tm_custom_event(session, created.id, with_reminder_id)

        remaining = delete_tm_custom_event(session, created.id, no_reminder_id)
        assert remaining is not None
        assert all(e.id != no_reminder_id for e in remaining)


def test_custom_event_reminders_surface_in_dashboard_list() -> None:
    with _make_session() as session:
        created = _create_application(session)
        add_tm_custom_event(
            session,
            created.id,
            TmCustomEventCreate(event_type="Notice u/s 132", event_date=date(2026, 3, 15), reminder_option="15d"),
        )
        rows = get_tm_applications(session)
        row = next(r for r in rows if r.id == created.id)
        assert any(r.kind == "custom_event" for r in row.upcoming_reminders)


def test_add_event_returns_none_for_missing_application() -> None:
    with _make_session() as session:
        result = add_tm_custom_event(
            session, 999, TmCustomEventCreate(event_type="Notice u/s 132", event_date=date(2026, 3, 15))
        )
        assert result is None


def test_close_event_rejects_wrong_application() -> None:
    with _make_session() as session:
        created_a = _create_application(session, "1234567")
        events_a = add_tm_custom_event(
            session,
            created_a.id,
            TmCustomEventCreate(event_type="Notice u/s 132", event_date=date(2026, 3, 15), reminder_option="15d"),
        )
        created_b = _create_application(session, "7654321")
        result = close_tm_custom_event(
            session, created_b.id, events_a[0].id, TmCustomEventClose(closure_date=date(2026, 2, 20))
        )
        assert result is None
