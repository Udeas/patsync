from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.audit.listener import register_audit_listener
from app.auth.models import AuditLog, User
from app.auth.security import hash_password
from app.database import get_session
from app.main import app

register_audit_listener()

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SQLModel.metadata.create_all(engine)


def _override():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = _override


def _seed_admin():
    with Session(engine) as session:
        if not session.exec(select(User).where(User.username == "admin")).first():
            session.add(User(username="admin", password_hash=hash_password("admin1234"), role="admin"))
            session.commit()


def test_successful_login_writes_audit() -> None:
    _seed_admin()
    client = TestClient(app)
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin1234"})
    assert resp.status_code == 200
    with Session(engine) as session:
        rows = session.exec(select(AuditLog).where(AuditLog.action == "login")).all()
        assert len(rows) >= 1
        assert rows[-1].actor_username == "admin"


def test_failed_login_writes_audit() -> None:
    _seed_admin()
    client = TestClient(app)
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401
    with Session(engine) as session:
        rows = session.exec(select(AuditLog).where(AuditLog.action == "login_failed")).all()
        assert len(rows) >= 1
        assert rows[-1].actor_username == "admin"
        assert rows[-1].actor_user_id is None
