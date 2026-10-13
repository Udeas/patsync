"""Design project notes: add, edit, list via project detail - mirrors trademark project notes."""

from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models.applications import Status
from app.schemas.applications import ApplicationCreate, ProjectNoteInput
from app.services.application_service import add_project_note, create_application, get_project_detail, update_project_note
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


def test_add_note_returns_full_notes_list() -> None:
    with _make_session() as session:
        created = _create_application(session)
        notes = add_project_note(session, created.id, ProjectNoteInput(note_text="First note"))
        assert notes is not None
        assert len(notes) == 1
        assert notes[0].note_text == "First note"


def test_notes_are_newest_first() -> None:
    with _make_session() as session:
        created = _create_application(session)
        add_project_note(session, created.id, ProjectNoteInput(note_text="Older"))
        notes = add_project_note(session, created.id, ProjectNoteInput(note_text="Newer"))
        assert notes is not None
        assert [n.note_text for n in notes] == ["Newer", "Older"]


def test_add_note_rejects_blank_text() -> None:
    with _make_session() as session:
        created = _create_application(session)
        with pytest.raises(ValueError, match="Note text is required"):
            add_project_note(session, created.id, ProjectNoteInput(note_text="   "))


def test_add_note_returns_none_for_missing_application() -> None:
    with _make_session() as session:
        result = add_project_note(session, 999, ProjectNoteInput(note_text="test"))
        assert result is None


def test_update_note_edits_existing_note() -> None:
    with _make_session() as session:
        created = _create_application(session)
        notes = add_project_note(session, created.id, ProjectNoteInput(note_text="Original"))
        note_id = notes[0].id
        updated = update_project_note(session, created.id, note_id, ProjectNoteInput(note_text="Edited"))
        assert updated is not None
        assert updated[0].note_text == "Edited"


def test_update_note_returns_none_for_wrong_application() -> None:
    with _make_session() as session:
        created_a = _create_application(session, "100001-001")
        notes_a = add_project_note(session, created_a.id, ProjectNoteInput(note_text="A's note"))

        second = _create_application(session, "100002-001")
        result = update_project_note(session, second.id, notes_a[0].id, ProjectNoteInput(note_text="hijack"))
        assert result is None


def test_project_detail_includes_notes() -> None:
    with _make_session() as session:
        created = _create_application(session)
        add_project_note(session, created.id, ProjectNoteInput(note_text="Detail visible note"))
        detail = get_project_detail(session, created.id)
        assert detail is not None
        assert len(detail.notes) == 1
        assert detail.notes[0].note_text == "Detail visible note"
