"""Client type checkboxes (patent/trademark/design) on PatentClient."""

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.patents.schemas import PatentClientInput, PatentClientUpdate
from app.patents.service import create_patent_client, list_patent_clients, update_patent_client


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _client_payload(**overrides) -> PatentClientInput:
    defaults = dict(
        client_code="ACME",
        name="Acme Corp",
        address=None,
        email=None,
        key_contacts=[],
        docketing_email=None,
        client_types=["patent"],
    )
    defaults.update(overrides)
    return PatentClientInput(**defaults)


def test_create_client_round_trips_client_types():
    with _make_session() as session:
        created = create_patent_client(session, _client_payload(client_types=["patent", "trademark"]))
        assert created["client_types"] == ["patent", "trademark"]

        [listed] = list_patent_clients(session)
        assert listed["client_types"] == ["patent", "trademark"]


def test_create_client_rejects_empty_client_types():
    with _make_session() as session:
        with pytest.raises(ValueError, match="at least one client type"):
            create_patent_client(session, _client_payload(client_types=[]))


def test_create_client_rejects_unknown_client_type():
    with _make_session() as session:
        with pytest.raises(ValueError, match="Unknown client type"):
            create_patent_client(session, _client_payload(client_types=["patent", "utility-model"]))


def test_update_client_changes_client_types():
    with _make_session() as session:
        created = create_patent_client(session, _client_payload(client_types=["patent"]))

        updated = update_patent_client(
            session,
            created["id"],
            PatentClientUpdate(
                client_code="ACME",
                name="Acme Corp",
                key_contacts=[],
                client_types=["design"],
            ),
        )
        assert updated is not None
        assert updated["client_types"] == ["design"]

        [listed] = list_patent_clients(session)
        assert listed["client_types"] == ["design"]


def test_update_client_rejects_empty_client_types():
    with _make_session() as session:
        created = create_patent_client(session, _client_payload(client_types=["patent"]))

        with pytest.raises(ValueError, match="at least one client type"):
            update_patent_client(
                session,
                created["id"],
                PatentClientUpdate(client_code="ACME", name="Acme Corp", key_contacts=[], client_types=[]),
            )
