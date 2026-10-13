"""Design custom events: create (with/without reminder), close, delete, reminder surfacing."""

from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models.applications import Status
from app.schemas.applications import ApplicationCreate, CustomEventClose, CustomEventCreate
from app.services.application_service import (
    add_custom_event,
    close_custom_event,
    create_application,
    delete_custom_event,
    get_application_by_id,
    get_applications,
    get_project_detail,
)
from app.status_catalog import STATUS_ID_APPLICATION_FILED


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(Status(id=STATUS_ID_APPLICATION_FILED, status="Application Filed"))
    session.commit()
    return session


def _create_application(session: Session, application_number: str = "100001-001"):
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


def test_no_reminder_event_is_added_without_reminder_date() -> None:
    with _make_session() as session:
        created = _create_application(session)
        events = add_custom_event(
            session, created.id, CustomEventCreate(event_type="Hearing", event_date=date(2026, 3, 15))
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
            events = add_custom_event(
                session,
                created.id,
                CustomEventCreate(event_type="Hearing", event_date=date(2026, 3, 15), reminder_option=option),
            )
            match = next(e for e in events if e.reminder_option == option)
            assert match.reminder_date == expected


def test_custom_event_surfaces_in_project_detail_and_reminders() -> None:
    with _make_session() as session:
        created = _create_application(session)
        add_custom_event(
            session,
            created.id,
            CustomEventCreate(event_type="Hearing", event_date=date(2026, 3, 15), reminder_option="15d"),
        )
        detail = get_project_detail(session, created.id)
        assert len(detail.custom_events) == 1
        assert any(r.kind == "custom_event" for r in detail.upcoming_reminders)


def test_closing_event_removes_it_from_reminders_but_keeps_it_in_custom_events() -> None:
    with _make_session() as session:
        created = _create_application(session)
        events = add_custom_event(
            session,
            created.id,
            CustomEventCreate(event_type="Hearing", event_date=date(2026, 3, 15), reminder_option="1m"),
        )
        event_id = events[0].id
        closed = close_custom_event(session, created.id, event_id, CustomEventClose(closure_date=date(2026, 2, 20)))
        assert closed[0].closure_date == date(2026, 2, 20)

        detail = get_project_detail(session, created.id)
        assert len(detail.custom_events) == 1
        assert not any(r.kind == "custom_event" for r in detail.upcoming_reminders)


def test_closing_already_closed_event_raises() -> None:
    with _make_session() as session:
        created = _create_application(session)
        events = add_custom_event(
            session,
            created.id,
            CustomEventCreate(event_type="Hearing", event_date=date(2026, 3, 15), reminder_option="15d"),
        )
        event_id = events[0].id
        close_custom_event(session, created.id, event_id, CustomEventClose(closure_date=date(2026, 2, 20)))
        with pytest.raises(ValueError, match="already closed"):
            close_custom_event(session, created.id, event_id, CustomEventClose(closure_date=date(2026, 2, 21)))


def test_delete_allowed_only_for_open_no_reminder_events() -> None:
    with _make_session() as session:
        created = _create_application(session)
        no_reminder = add_custom_event(session, created.id, CustomEventCreate(event_type="Hearing", event_date=date(2026, 3, 15)))
        no_reminder_id = no_reminder[0].id

        with_reminder = add_custom_event(
            session,
            created.id,
            CustomEventCreate(event_type="Hearing", event_date=date(2026, 4, 1), reminder_option="15d"),
        )
        with_reminder_id = next(e.id for e in with_reminder if e.reminder_option == "15d")

        with pytest.raises(ValueError, match="Only open, no-reminder events"):
            delete_custom_event(session, created.id, with_reminder_id)

        remaining = delete_custom_event(session, created.id, no_reminder_id)
        assert remaining is not None
        assert all(e.id != no_reminder_id for e in remaining)


def test_custom_event_reminders_surface_in_dashboard_list() -> None:
    with _make_session() as session:
        created = _create_application(session)
        add_custom_event(
            session,
            created.id,
            CustomEventCreate(event_type="Hearing", event_date=date(2026, 3, 15), reminder_option="15d"),
        )
        rows = get_applications(session)
        row = next(r for r in rows if r.id == created.id)
        assert any(r.kind == "custom_event" for r in row.upcoming_reminders)


def test_add_event_returns_none_for_missing_application() -> None:
    with _make_session() as session:
        result = add_custom_event(session, 999, CustomEventCreate(event_type="Hearing", event_date=date(2026, 3, 15)))
        assert result is None


def test_close_event_rejects_wrong_application() -> None:
    with _make_session() as session:
        created_a = _create_application(session, "100001-001")
        events_a = add_custom_event(
            session,
            created_a.id,
            CustomEventCreate(event_type="Hearing", event_date=date(2026, 3, 15), reminder_option="15d"),
        )
        created_b = _create_application(session, "100002-001")
        result = close_custom_event(session, created_b.id, events_a[0].id, CustomEventClose(closure_date=date(2026, 2, 20)))
        assert result is None


def test_get_application_by_id_includes_custom_event_reminder() -> None:
    with _make_session() as session:
        created = _create_application(session)
        add_custom_event(
            session,
            created.id,
            CustomEventCreate(event_type="Hearing", event_date=date(2026, 3, 15), reminder_option="15d"),
        )
        fetched = get_application_by_id(session, created.id)
        assert any(r.kind == "custom_event" for r in fetched.upcoming_reminders)
