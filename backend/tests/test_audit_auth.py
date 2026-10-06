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


def test_authenticated_mutation_is_attributed_to_actor_not_just_login() -> None:
    # Regression test: get_current_user/require_admin used to be plain `def`
    # dependencies, which FastAPI dispatches through a threadpool hop with its
    # own copy of the request's contextvars. set_actor() there mutated a
    # throwaway copy that never reached the (separately threadpool-dispatched)
    # sync endpoint body, so every audit row written outside the login
    # endpoint - which sets its actor directly from the login payload, not via
    # the contextvar - silently had no actor. A call via TestClient exercises
    # the real threadpool dispatch, which a direct function-call test (e.g.
    # test_audit_status.py) would not.
    _seed_admin()
    client = TestClient(app)
    login_resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin1234"})
    token = login_resp.json()["access_token"]

    create_resp = client.post(
        "/api/patents/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "project_mode": "final",
            "application_type": "Ordinary Application",
            "docket_no": "ACTOR-PROPAGATION-1",
            "in_application_no": "202511019999",
            "in_application_date": "2025-11-01",
            "applicant_name": "Acme",
            "applicant_country": "IN",
            "applicant_address": "Addr",
            "applicants": [{"name": "Acme", "country": "IN", "address": "Addr"}],
            "inventors": [{"name": "Inv A", "nationality": "IN", "address": "Inv Addr"}],
            "priorities": [],
            "international_applications": [],
        },
    )
    assert create_resp.status_code == 200, create_resp.text

    with Session(engine) as session:
        rows = session.exec(
            select(AuditLog).where(AuditLog.entity_type == "patent", AuditLog.action == "create")
        ).all()
        assert len(rows) >= 1
        assert rows[-1].actor_username == "admin"
