"""Trademark project notes: add, edit, list via project detail - mirrors patent project notes."""

from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models.trademark import TmStatus
from app.schemas.trademark import TmApplicationCreate, TmProjectNoteInput
from app.services.trademark_service import (
    add_project_note,
    create_tm_application,
    get_tm_project_detail,
    update_project_note,
)
from app.tm_status_catalog import STATUS_ID_TM_APPLICATION_FILED


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(TmStatus(id=STATUS_ID_TM_APPLICATION_FILED, status="Application filed"))
    session.commit()
    return session


def _create_application(session: Session):
    return create_tm_application(
        session,
        TmApplicationCreate(
            application_number="1234567",
            application_date=date(2025, 1, 10),
            applicant_name="Client",
            applicant_type="Individual",
            tm_name="Mark",
            tm_type="Wordmark",
            tm_class="5",
            tm_usage_status="Proposed to be used",
            applicant_address="Address",
        ),
    )


def test_add_note_returns_full_notes_list() -> None:
    with _make_session() as session:
        created = _create_application(session)
        notes = add_project_note(session, created.id, TmProjectNoteInput(note_text="First note"))
        assert notes is not None
        assert len(notes) == 1
        assert notes[0].note_text == "First note"


def test_notes_are_newest_first() -> None:
    with _make_session() as session:
        created = _create_application(session)
        add_project_note(session, created.id, TmProjectNoteInput(note_text="Older"))
        notes = add_project_note(session, created.id, TmProjectNoteInput(note_text="Newer"))
        assert notes is not None
        assert [n.note_text for n in notes] == ["Newer", "Older"]


def test_add_note_rejects_blank_text() -> None:
    with _make_session() as session:
        created = _create_application(session)
        with pytest.raises(ValueError, match="Note text is required"):
            add_project_note(session, created.id, TmProjectNoteInput(note_text="   "))


def test_add_note_returns_none_for_missing_application() -> None:
    with _make_session() as session:
        result = add_project_note(session, 999, TmProjectNoteInput(note_text="test"))
        assert result is None


def test_update_note_edits_existing_note() -> None:
    with _make_session() as session:
        created = _create_application(session)
        notes = add_project_note(session, created.id, TmProjectNoteInput(note_text="Original"))
        note_id = notes[0].id
        updated = update_project_note(session, created.id, note_id, TmProjectNoteInput(note_text="Edited"))
        assert updated is not None
        assert updated[0].note_text == "Edited"


def test_update_note_returns_none_for_wrong_application() -> None:
    with _make_session() as session:
        created_a = _create_application(session)
        notes_a = add_project_note(session, created_a.id, TmProjectNoteInput(note_text="A's note"))

        second = create_tm_application(
            session,
            TmApplicationCreate(
                application_number="7654321",
                application_date=date(2025, 2, 1),
                applicant_name="Other",
                applicant_type="Company",
                tm_name="OtherMark",
                tm_type="Device/Logo",
                tm_class="9",
                tm_usage_status="Proposed to be used",
                applicant_address="Other address",
            ),
        )
        result = update_project_note(session, second.id, notes_a[0].id, TmProjectNoteInput(note_text="hijack"))
        assert result is None


def test_project_detail_includes_notes() -> None:
    with _make_session() as session:
        created = _create_application(session)
        add_project_note(session, created.id, TmProjectNoteInput(note_text="Detail visible note"))
        detail = get_tm_project_detail(session, created.id)
        assert detail is not None
        assert len(detail.notes) == 1
        assert detail.notes[0].note_text == "Detail visible note"
