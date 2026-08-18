import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
from app.auth.schemas import UserCreate
from app.auth.service import create_user, seed_admin
from app.database import get_session


@pytest.fixture()
def client():
    # StaticPool forces a single shared connection so the in-memory DB
    # is not recreated on every new Session() call.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def _override_session():
        with Session(engine) as session:
            yield session

    with Session(engine) as session:
        seed_admin(session, "admin", "admin-pass")
        create_user(session, UserCreate(username="user1", password="secret12", role="user"))

    main_module.app.dependency_overrides[get_session] = _override_session
    yield TestClient(main_module.app)
    main_module.app.dependency_overrides.clear()


def _token(client, username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_login_success_returns_token_and_user(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin-pass"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "admin"


def test_login_bad_password_401(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
    token = _token(client, "user1", "secret12")
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "user1"


def test_protected_data_route_requires_token(client):
    assert client.get("/api/status/").status_code == 401
    token = _token(client, "user1", "secret12")
    resp = client.get("/api/status/", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_admin_gate_on_create_user(client):
    user_token = _token(client, "user1", "secret12")
    denied = client.post(
        "/api/auth/users",
        json={"username": "x", "password": "secret12"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert denied.status_code == 403

    admin_token = _token(client, "admin", "admin-pass")
    ok = client.post(
        "/api/auth/users",
        json={"username": "newbie", "password": "secret12", "display_name": "Newbie"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert ok.status_code == 201
    assert ok.json()["username"] == "newbie"


def test_health_stays_open(client):
    assert client.get("/api/health").status_code == 200
