from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.auth.deps import get_current_user, require_admin
from app.auth.models import AuditLog, User
from app.database import get_session
from app.main import app

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

_admin = User(id=1, username="admin", password_hash="x", role="admin")


def _seed_rows():
    with Session(engine) as session:
        session.add(AuditLog(created_at=datetime.utcnow(), actor_username="admin",
                             action="create", entity_type="patent", entity_id=1, entity_label="D1",
                             changes="[]"))
        session.add(AuditLog(created_at=datetime.utcnow(), actor_username="admin",
                             action="update", entity_type="design", entity_id=2, entity_label="D2",
                             changes='[{"field":"x","old":1,"new":2}]'))
        session.commit()


def test_requires_admin() -> None:
    prior = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[require_admin] = lambda: (_ for _ in ()).throw(
        __import__("fastapi").HTTPException(status_code=403, detail="Admin privileges required")
    )
    client = TestClient(app)
    assert client.get("/api/audit").status_code == 403
    app.dependency_overrides.pop(require_admin, None)
    if prior is None:
        app.dependency_overrides.pop(get_session, None)
    else:
        app.dependency_overrides[get_session] = prior


def _seed_search_rows():
    with Session(engine) as session:
        session.add(AuditLog(created_at=datetime.utcnow(), actor_username="rahul",
                             action="status_change", entity_type="patent", entity_id=3, entity_label="PA9999",
                             changes='[{"field":"status","old":"Pending","new":"Granted"}]'))
        session.add(AuditLog(created_at=datetime.utcnow(), actor_username="priya",
                             action="update", entity_type="trademark", entity_id=4, entity_label="TM0001",
                             changes='[{"field":"tm_name","old":"Old Co","new":"New Co"}]'))
        session.commit()


def test_free_text_search_matches_label_and_changes() -> None:
    prior = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = _override
    _seed_search_rows()
    app.dependency_overrides[require_admin] = lambda: _admin
    client = TestClient(app)

    by_label = client.get("/api/audit", params={"q": "PA9999"}).json()
    assert all(i["entity_label"] == "PA9999" for i in by_label["items"])
    assert by_label["total"] >= 1

    by_change_value = client.get("/api/audit", params={"q": "granted"}).json()
    assert any(i["entity_label"] == "PA9999" for i in by_change_value["items"])

    app.dependency_overrides.pop(require_admin, None)
    if prior is None:
        app.dependency_overrides.pop(get_session, None)
    else:
        app.dependency_overrides[get_session] = prior


def test_project_and_field_filters() -> None:
    prior = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = _override
    _seed_search_rows()
    app.dependency_overrides[require_admin] = lambda: _admin
    client = TestClient(app)

    by_project = client.get("/api/audit", params={"project": "tm0001"}).json()
    assert all(i["entity_label"] == "TM0001" for i in by_project["items"])
    assert by_project["total"] >= 1

    by_field = client.get("/api/audit", params={"field": "tm_name"}).json()
    assert all(
        any(c["field"] == "tm_name" for c in i["changes"]) for i in by_field["items"]
    )

    app.dependency_overrides.pop(require_admin, None)
    if prior is None:
        app.dependency_overrides.pop(get_session, None)
    else:
        app.dependency_overrides[get_session] = prior


def test_sort_dir_asc_reverses_order() -> None:
    prior = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = _override
    _seed_rows()
    app.dependency_overrides[require_admin] = lambda: _admin
    client = TestClient(app)

    resp = client.get("/api/audit", params={"sort_dir": "asc"})
    items = resp.json()["items"]
    assert items[0]["id"] < items[-1]["id"]

    app.dependency_overrides.pop(require_admin, None)
    if prior is None:
        app.dependency_overrides.pop(get_session, None)
    else:
        app.dependency_overrides[get_session] = prior


def test_lists_newest_first_and_filters() -> None:
    prior = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = _override
    _seed_rows()
    app.dependency_overrides[require_admin] = lambda: _admin
    client = TestClient(app)
    resp = client.get("/api/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    assert body["items"][0]["id"] > body["items"][-1]["id"]  # newest first
    resp2 = client.get("/api/audit", params={"entity_type": "design"})
    assert all(i["entity_type"] == "design" for i in resp2.json()["items"])
    design_item = next(i for i in resp2.json()["items"] if i["entity_id"] == 2)
    assert design_item["changes"] == [{"field": "x", "old": 1, "new": 2}]
    app.dependency_overrides.pop(require_admin, None)
    if prior is None:
        app.dependency_overrides.pop(get_session, None)
    else:
        app.dependency_overrides[get_session] = prior
