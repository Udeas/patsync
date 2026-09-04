"""Patent custom events: create (with/without reminder), close, delete, reminder surfacing."""

from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.patents.schemas import PatentCustomEventClose, PatentCustomEventCreate, PatentProjectCreate
from app.patents.service import (
    add_patent_custom_event,
    close_patent_custom_event,
    create_project,
    delete_patent_custom_event,
    get_project,
    list_projects,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _create_project(session: Session, docket_no: str = "DCKT-EVT-1") -> dict:
    return create_project(
        session,
        PatentProjectCreate(
            project_mode="draft",
            application_type="Provisional Application",
            docket_no=docket_no,
            applicant_name="Acme",
            applicant_country="IN",
            applicant_address="Address",
        ),
    )


def test_no_reminder_event_is_added_without_reminder_date() -> None:
    with _make_session() as session:
        project = _create_project(session)
        events = add_patent_custom_event(
            session,
            project["id"],
            PatentCustomEventCreate(event_type="Form-13 (amendment)", event_date=date(2026, 3, 15)),
        )
        assert events is not None
        assert len(events) == 1
        assert events[0].reminder_option == "none"
        assert events[0].reminder_date is None


def test_reminder_date_computed_for_each_option() -> None:
    with _make_session() as session:
        project = _create_project(session)
        for option, expected in [
            ("15d", date(2026, 3, 30)),
            ("1m", date(2026, 4, 15)),
            ("3m", date(2026, 6, 15)),
        ]:
            events = add_patent_custom_event(
                session,
                project["id"],
                PatentCustomEventCreate(
                    event_type="Form-13 (amendment)", event_date=date(2026, 3, 15), reminder_option=option
                ),
            )
            match = next(e for e in events if e.reminder_option == option)
            assert match.reminder_date == expected


def test_custom_event_surfaces_in_project_detail_and_reminders() -> None:
    with _make_session() as session:
        project = _create_project(session)
        add_patent_custom_event(
            session,
            project["id"],
            PatentCustomEventCreate(
                event_type="Form-13 (amendment)", event_date=date(2026, 3, 15), reminder_option="15d"
            ),
        )
        detail = get_project(session, project["id"])
        assert len(detail["custom_events"]) == 1
        assert len(detail["custom_event_reminders"]) == 1
        assert detail["custom_event_reminders"][0]["kind"] == "custom_event"


def test_closing_event_removes_it_from_reminders_but_keeps_it_in_custom_events() -> None:
    with _make_session() as session:
        project = _create_project(session)
        events = add_patent_custom_event(
            session,
            project["id"],
            PatentCustomEventCreate(
                event_type="Form-13 (amendment)", event_date=date(2026, 3, 15), reminder_option="1m"
            ),
        )
        event_id = events[0].id
        closed = close_patent_custom_event(
            session, project["id"], event_id, PatentCustomEventClose(closure_date=date(2026, 2, 20))
        )
        assert closed[0].closure_date == date(2026, 2, 20)

        detail = get_project(session, project["id"])
        assert len(detail["custom_events"]) == 1
        assert detail["custom_events"][0]["closure_date"] == date(2026, 2, 20)
        assert detail["custom_event_reminders"] == []


def test_closing_already_closed_event_raises() -> None:
    with _make_session() as session:
        project = _create_project(session)
        events = add_patent_custom_event(
            session,
            project["id"],
            PatentCustomEventCreate(event_type="Form-13 (amendment)", event_date=date(2026, 3, 15), reminder_option="15d"),
        )
        event_id = events[0].id
        close_patent_custom_event(session, project["id"], event_id, PatentCustomEventClose(closure_date=date(2026, 2, 20)))
        with pytest.raises(ValueError, match="already closed"):
            close_patent_custom_event(
                session, project["id"], event_id, PatentCustomEventClose(closure_date=date(2026, 2, 21))
            )


def test_delete_allowed_only_for_open_no_reminder_events() -> None:
    with _make_session() as session:
        project = _create_project(session)
        no_reminder = add_patent_custom_event(
            session, project["id"], PatentCustomEventCreate(event_type="Form-13 (amendment)", event_date=date(2026, 3, 15))
        )
        no_reminder_id = no_reminder[0].id

        with_reminder = add_patent_custom_event(
            session,
            project["id"],
            PatentCustomEventCreate(event_type="Form-13 (amendment)", event_date=date(2026, 4, 1), reminder_option="15d"),
        )
        with_reminder_id = next(e.id for e in with_reminder if e.reminder_option == "15d")

        with pytest.raises(ValueError, match="Only open, no-reminder events"):
            delete_patent_custom_event(session, project["id"], with_reminder_id)

        remaining = delete_patent_custom_event(session, project["id"], no_reminder_id)
        assert remaining is not None
        assert all(e.id != no_reminder_id for e in remaining)


def test_custom_event_reminders_surface_in_list_projects() -> None:
    with _make_session() as session:
        project = _create_project(session)
        add_patent_custom_event(
            session,
            project["id"],
            PatentCustomEventCreate(event_type="Form-13 (amendment)", event_date=date(2026, 3, 15), reminder_option="15d"),
        )
        rows = list_projects(session)
        row = next(r for r in rows if r["id"] == project["id"])
        assert len(row["custom_event_reminders"]) == 1


def test_add_event_returns_none_for_missing_project() -> None:
    with _make_session() as session:
        result = add_patent_custom_event(
            session, 999, PatentCustomEventCreate(event_type="Form-13 (amendment)", event_date=date(2026, 3, 15))
        )
        assert result is None


def test_close_event_rejects_wrong_project() -> None:
    with _make_session() as session:
        project_a = _create_project(session, "DCKT-EVT-A")
        events_a = add_patent_custom_event(
            session,
            project_a["id"],
            PatentCustomEventCreate(event_type="Form-13 (amendment)", event_date=date(2026, 3, 15), reminder_option="15d"),
        )
        project_b = _create_project(session, "DCKT-EVT-B")
        result = close_patent_custom_event(
            session, project_b["id"], events_a[0].id, PatentCustomEventClose(closure_date=date(2026, 2, 20))
        )
        assert result is None
