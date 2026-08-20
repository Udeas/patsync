import json

from sqlmodel import Session, SQLModel, create_engine, select

from app.audit.context import mark_explicit, set_actor
from app.audit.listener import register_audit_listener
from app.auth.models import AuditLog
from app.patents.models import PatentClient

register_audit_listener()


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _audits(session) -> list[AuditLog]:
    return session.exec(select(AuditLog).order_by(AuditLog.id)).all()


def test_create_logs_row_with_actor() -> None:
    with _session() as session:
        set_actor(3, "admin")
        session.add(PatentClient(client_code="AC", name="Acme"))
        session.commit()
        rows = _audits(session)
        assert len(rows) == 1
        assert rows[0].action == "create"
        assert rows[0].entity_type == "client"
        assert rows[0].entity_label == "Acme"
        assert rows[0].actor_user_id == 3
        assert rows[0].actor_username == "admin"
        assert json.loads(rows[0].changes) == []
        assert rows[0].entity_id is not None


def test_update_logs_field_diff() -> None:
    with _session() as session:
        set_actor(3, "admin")
        client = PatentClient(client_code="AC", name="Acme")
        session.add(client)
        session.commit()
        client.name = "Acme Corp"
        session.commit()
        rows = [r for r in _audits(session) if r.action == "update"]
        assert len(rows) == 1
        changes = json.loads(rows[0].changes)
        assert {"field": "name", "old": "Acme", "new": "Acme Corp"} in changes


def test_delete_logs_row() -> None:
    with _session() as session:
        client = PatentClient(client_code="AC", name="Acme")
        session.add(client)
        session.commit()
        eid = client.id
        session.delete(client)
        session.commit()
        rows = [r for r in _audits(session) if r.action == "delete"]
        assert len(rows) == 1
        assert rows[0].entity_id == eid
        assert rows[0].entity_type == "client"


def test_touch_only_change_is_skipped() -> None:
    with _session() as session:
        client = PatentClient(client_code="AC", name="Acme")
        session.add(client)
        session.commit()
        before = len(_audits(session))
        client.name = "Acme"
        session.commit()
        assert len(_audits(session)) == before


def test_non_audited_model_is_ignored() -> None:
    from app.auth.models import User

    with _session() as session:
        session.add(User(username="bob", password_hash="x"))
        session.commit()
        assert _audits(session) == []


def test_explicit_marker_suppresses_update() -> None:
    with _session() as session:
        client = PatentClient(client_code="AC", name="Acme")
        session.add(client)
        session.commit()
        mark_explicit(session, "client", client.id)
        client.name = "Acme Corp"
        session.commit()
        assert [r for r in _audits(session) if r.action == "update"] == []
