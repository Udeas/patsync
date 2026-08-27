"""Project Notes: a simple dated bullet log shown on the docket detail screen."""

from sqlmodel import Session, SQLModel, create_engine

from app.patents.schemas import PatentProjectCreate, PatentProjectNoteInput
from app.patents.service import add_project_note, create_project, get_project

import pytest


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _create_project(session: Session) -> dict:
    return create_project(
        session,
        PatentProjectCreate(
            project_mode="draft",
            application_type="Convention",
            docket_no="NOTE-1",
            applicant_name="Acme Corp",
        ),
    )


def test_new_project_has_no_notes():
    with _make_session() as session:
        project = _create_project(session)
        row = get_project(session, project["id"])
        assert row["notes"] == []


def test_add_project_note_returns_it_newest_first():
    with _make_session() as session:
        project = _create_project(session)

        notes = add_project_note(session, project["id"], PatentProjectNoteInput(note_text="Called client re: RFE"))
        assert len(notes) == 1
        assert notes[0].note_text == "Called client re: RFE"
        assert notes[0].created_date is not None

        notes = add_project_note(session, project["id"], PatentProjectNoteInput(note_text="Filed response"))
        assert len(notes) == 2
        # newest first
        assert notes[0].note_text == "Filed response"
        assert notes[1].note_text == "Called client re: RFE"


def test_notes_surface_on_the_project_detail_response():
    with _make_session() as session:
        project = _create_project(session)
        add_project_note(session, project["id"], PatentProjectNoteInput(note_text="First note"))

        row = get_project(session, project["id"])
        assert len(row["notes"]) == 1
        assert row["notes"][0]["note_text"] == "First note"


def test_blank_note_is_rejected():
    with _make_session() as session:
        project = _create_project(session)
        with pytest.raises(ValueError):
            add_project_note(session, project["id"], PatentProjectNoteInput(note_text="   "))


def test_add_note_to_missing_project_returns_none():
    with _make_session() as session:
        assert add_project_note(session, 9999, PatentProjectNoteInput(note_text="x")) is None
