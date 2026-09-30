from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine, select

from app.auth.models import AuditLog


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_audit_log_row_roundtrips() -> None:
    with _session() as session:
        session.add(
            AuditLog(
                created_at=datetime.utcnow(),
                actor_user_id=1,
                actor_username="admin",
                action="update",
                entity_type="patent",
                entity_id=7,
                entity_label="DCKT-1",
                changes='[{"field": "docket_no", "old": "A", "new": "B"}]',
                ip_address=None,
            )
        )
        session.commit()
        row = session.exec(select(AuditLog)).one()
        assert row.action == "update"
        assert row.entity_type == "patent"
        assert row.entity_id == 7
        assert row.entity_label == "DCKT-1"
        assert '"docket_no"' in row.changes
