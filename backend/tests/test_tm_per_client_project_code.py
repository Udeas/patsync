"""Trademark project_code, when a client is selected, is CLIENTCODE + a
sequential number tracked per client (e.g. ABC01, ABC02, ...), never reused
across different clients. With no client selected, the legacy global
TM<4-digit> scheme still applies."""

from datetime import date

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models.trademark import TmStatus
from app.patents.models import PatentClient
from app.schemas.trademark import TmApplicationCreate
from app.services.trademark_service import create_tm_application
from app.tm_status_catalog import STATUS_ID_TM_APPLICATION_FILED


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(TmStatus(id=STATUS_ID_TM_APPLICATION_FILED, status="Application filed"))
    session.commit()
    return session


def _make_client(session: Session, client_code: str, name: str) -> int:
    client = PatentClient(client_code=client_code, name=name)
    session.add(client)
    session.commit()
    session.refresh(client)
    return client.id


def _create(session: Session, application_number: str, client_id: int | None = None):
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
            tm_usage_status="Proposed to be used",
            applicant_address="Address",
            client_id=client_id,
        ),
    )


def test_first_project_for_client_gets_code01() -> None:
    with _make_session() as session:
        client_id = _make_client(session, "ABC", "ABC Private Limited")
        created = _create(session, "1000001", client_id=client_id)
        assert created.project_code == "ABC01"


def test_project_codes_increment_sequentially_per_client() -> None:
    with _make_session() as session:
        client_id = _make_client(session, "ABC", "ABC Private Limited")
        first = _create(session, "1000001", client_id=client_id)
        second = _create(session, "1000002", client_id=client_id)
        third = _create(session, "1000003", client_id=client_id)
        assert [first.project_code, second.project_code, third.project_code] == [
            "ABC01",
            "ABC02",
            "ABC03",
        ]


def test_different_clients_have_independent_sequences() -> None:
    with _make_session() as session:
        abc_id = _make_client(session, "ABC", "ABC Private Limited")
        xyz_id = _make_client(session, "XYZ", "XYZ Industries")

        abc_first = _create(session, "1000001", client_id=abc_id)
        xyz_first = _create(session, "1000002", client_id=xyz_id)
        abc_second = _create(session, "1000003", client_id=abc_id)
        xyz_second = _create(session, "1000004", client_id=xyz_id)

        assert abc_first.project_code == "ABC01"
        assert xyz_first.project_code == "XYZ01"
        assert abc_second.project_code == "ABC02"
        assert xyz_second.project_code == "XYZ02"


def test_no_client_selected_falls_back_to_legacy_global_scheme() -> None:
    with _make_session() as session:
        first = _create(session, "1000001")
        second = _create(session, "1000002")
        assert first.project_code == "TM0001"
        assert second.project_code == "TM0002"


def test_invalid_client_id_raises_value_error() -> None:
    with _make_session() as session:
        with pytest.raises(ValueError, match="client_id does not reference an existing client"):
            _create(session, "1000001", client_id=999)
