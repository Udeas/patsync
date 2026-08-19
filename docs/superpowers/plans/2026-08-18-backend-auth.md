# Backend Auth Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the frontend mock login with real backend JWT authentication, a seeded admin (no public signup), and token-protected `/api/*` data routes.

**Architecture:** New FastAPI `app/auth/` module (models, schemas, security, deps, service, router) persists users in the shared Postgres DB with bcrypt-hashed passwords and issues HS256 JWTs. `main.py` gates existing data routers behind `get_current_user`. The Angular `AuthService` is rewritten to call the backend; an HTTP interceptor attaches the bearer token and handles 401.

**Tech Stack:** FastAPI, SQLModel, Postgres/SQLite (shared engine), `passlib[bcrypt]`, `python-jose[cryptography]`, pytest + httpx; Angular (standalone, signals), Karma/Jasmine.

## Global Constraints

- Python `>=3.13`; backend dep declarations live in `backend/pyproject.toml`.
- Follow existing router/service split; services take a `Session` and are unit-tested against in-memory SQLite (`create_engine("sqlite:///:memory:")`).
- Migrations are idempotent (`CREATE TABLE IF NOT EXISTS`) and added to `app/database.py` `run_schema_migrations`, with BOTH a Postgres and a SQLite branch.
- JWT: `HS256`, claim `sub` = username, `exp` from `ACCESS_TOKEN_EXPIRE_MINUTES` (default 480).
- Never ship a hardcoded real password. Admin seed reads `AUTH_ADMIN_USERNAME` / `AUTH_ADMIN_PASSWORD`.
- Frontend API base: `` `${environment.apiBaseUrl}/api/auth` ``. Token localStorage key: `patsync.auth.token`.
- All backend commits on branch `feat/backend-auth`.

---

### Task 1: Dependencies + auth settings

**Files:**
- Modify: `backend/pyproject.toml` (dependencies list)
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/test_auth_settings.py`

**Interfaces:**
- Produces: `app.core.config.settings` gains `SECRET_KEY: str`, `ALGORITHM: str = "HS256"`, `ACCESS_TOKEN_EXPIRE_MINUTES: int = 480`, `AUTH_ADMIN_USERNAME: str | None = None`, `AUTH_ADMIN_PASSWORD: str | None = None`.

- [ ] **Step 1: Add backend dependencies**

Edit `backend/pyproject.toml`, add to the `dependencies` array:

```toml
    "passlib[bcrypt]>=1.7.4",
    "python-jose[cryptography]>=3.3.0",
```

- [ ] **Step 2: Install**

Run: `cd backend && uv sync` (or `pip install -e ".[dev]"`)
Expected: resolves and installs `passlib`, `python-jose`.

- [ ] **Step 3: Write the failing test**

Create `backend/tests/test_auth_settings.py`:

```python
import importlib


def test_settings_expose_auth_fields(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret")
    import app.core.config as config
    importlib.reload(config)
    s = config.Settings()
    assert s.SECRET_KEY == "unit-test-secret"
    assert s.ALGORITHM == "HS256"
    assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 480
    assert s.AUTH_ADMIN_USERNAME is None
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd backend && pytest tests/test_auth_settings.py -v`
Expected: FAIL (`Settings` has no `SECRET_KEY` / validation error).

- [ ] **Step 5: Extend Settings**

Edit `backend/app/core/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    APP_PORT: int = 8000
    DEBUG: bool = True

    SECRET_KEY: str = "dev-insecure-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    AUTH_ADMIN_USERNAME: str | None = None
    AUTH_ADMIN_PASSWORD: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
```

Note: `SECRET_KEY` has a dev default so tests and local runs work without env setup; startup (Task 5) refuses the default when `DEBUG` is false.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/test_auth_settings.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py backend/tests/test_auth_settings.py
git commit -m "feat(auth): add auth settings and passlib/python-jose deps"
```

---

### Task 2: User model + migration

**Files:**
- Create: `backend/app/auth/__init__.py` (empty)
- Create: `backend/app/auth/models.py`
- Modify: `backend/app/database.py` (add `_run_users_migration`, call it in `run_schema_migrations`)
- Modify: `backend/app/main.py` (import `User` so `create_all` registers it)
- Test: `backend/tests/test_auth_model.py`

**Interfaces:**
- Produces: `app.auth.models.User` SQLModel with fields `id`, `username`, `display_name`, `password_hash`, `role`, `is_active`, `created_at`, `updated_at`; `__tablename__ = "users"`.
- Produces: `app.database._run_users_migration(conn, backend: str) -> None`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth_model.py`:

```python
from sqlmodel import Session, SQLModel, create_engine

from app.auth.models import User


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_user_persists_with_defaults() -> None:
    with _session() as session:
        user = User(username="admin", display_name="Admin", password_hash="x")
        session.add(user)
        session.commit()
        session.refresh(user)
        assert user.id is not None
        assert user.role == "user"
        assert user.is_active is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_auth_model.py -v`
Expected: FAIL (`ModuleNotFoundError: app.auth`).

- [ ] **Step 3: Create the package and model**

Create empty `backend/app/auth/__init__.py`.

Create `backend/app/auth/models.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(max_length=64, unique=True, index=True)
    display_name: str = Field(default="", max_length=128)
    password_hash: str = Field(max_length=255)
    role: str = Field(default="user", max_length=16)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_auth_model.py -v`
Expected: PASS

- [ ] **Step 5: Add the raw migration (both backends)**

In `backend/app/database.py`, add this function above `run_schema_migrations`:

```python
def _run_users_migration(conn, backend: str) -> None:
    if backend == "postgresql":
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(64) NOT NULL UNIQUE,
                    display_name VARCHAR(128) NOT NULL DEFAULT '',
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(16) NOT NULL DEFAULT 'user',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username_lower "
                "ON users (lower(username))"
            )
        )
    else:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL DEFAULT '',
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """
            )
        )
```

Then, inside `run_schema_migrations`, add the call alongside the other migrations (after `_run_uspto_tracker_migration(conn, backend)`):

```python
        _run_users_migration(conn, backend)
```

- [ ] **Step 6: Register the model for create_all**

In `backend/app/main.py`, add near the other model imports (after `from app.us_pto.models import UsptoTracker  # noqa: F401`):

```python
from app.auth.models import User  # noqa: F401
```

- [ ] **Step 7: Run the full test suite**

Run: `cd backend && pytest tests/test_auth_model.py tests/test_auth_settings.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/auth/__init__.py backend/app/auth/models.py backend/app/database.py backend/app/main.py backend/tests/test_auth_model.py
git commit -m "feat(auth): add users table model and migration"
```

---

### Task 3: Security primitives (hashing + JWT)

**Files:**
- Create: `backend/app/auth/security.py`
- Test: `backend/tests/test_auth_security.py`

**Interfaces:**
- Produces: `hash_password(plain: str) -> str`
- Produces: `verify_password(plain: str, hashed: str) -> bool`
- Produces: `create_access_token(subject: str, expires_minutes: int | None = None) -> str`
- Produces: `decode_access_token(token: str) -> str | None` (returns the `sub`/username, or `None` if invalid/expired)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth_security.py`:

```python
import time

from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_roundtrip() -> None:
    hashed = hash_password("secret12")
    assert hashed != "secret12"
    assert verify_password("secret12", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_token_roundtrip() -> None:
    token = create_access_token("admin")
    assert decode_access_token(token) == "admin"


def test_token_garbage_returns_none() -> None:
    assert decode_access_token("not.a.token") is None


def test_token_expired_returns_none() -> None:
    token = create_access_token("admin", expires_minutes=-1)
    time.sleep(0.01)
    assert decode_access_token(token) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_auth_security.py -v`
Expected: FAIL (`ModuleNotFoundError: app.auth.security`).

- [ ] **Step 3: Implement security.py**

Create `backend/app/auth/security.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except ValueError:
        return False


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    minutes = (
        expires_minutes
        if expires_minutes is not None
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_auth_security.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth/security.py backend/tests/test_auth_security.py
git commit -m "feat(auth): add bcrypt hashing and JWT helpers"
```

---

### Task 4: Schemas + service (authenticate, create_user, seed_admin)

**Files:**
- Create: `backend/app/auth/schemas.py`
- Create: `backend/app/auth/service.py`
- Test: `backend/tests/test_auth_service.py`

**Interfaces:**
- Consumes: `User` (Task 2); `hash_password`, `verify_password` (Task 3).
- Produces schemas: `LoginRequest{username,password}`, `TokenResponse{access_token, token_type, user}`, `UserCreate{username, password, display_name, role}`, `UserOut{id, username, display_name, role, is_active}`.
- Produces service fns:
  - `get_user_by_username(session, username) -> User | None` (case-insensitive)
  - `authenticate(session, username, password) -> User | None` (None if no user / bad password / inactive)
  - `create_user(session, data: UserCreate) -> User` (raises `ValueError` on duplicate username)
  - `seed_admin(session, username, password) -> User | None` (creates admin if none exists; returns created user or None)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth_service.py`:

```python
import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.auth.schemas import UserCreate
from app.auth.service import authenticate, create_user, get_user_by_username, seed_admin


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_create_and_authenticate() -> None:
    with _session() as session:
        create_user(session, UserCreate(username="Alice", password="secret12", display_name="Alice"))
        assert authenticate(session, "alice", "secret12") is not None
        assert authenticate(session, "alice", "wrong") is None


def test_duplicate_username_rejected() -> None:
    with _session() as session:
        create_user(session, UserCreate(username="bob", password="secret12"))
        with pytest.raises(ValueError):
            create_user(session, UserCreate(username="BOB", password="secret12"))


def test_inactive_user_cannot_authenticate() -> None:
    with _session() as session:
        user = create_user(session, UserCreate(username="carol", password="secret12"))
        user.is_active = False
        session.add(user)
        session.commit()
        assert authenticate(session, "carol", "secret12") is None


def test_seed_admin_is_idempotent() -> None:
    with _session() as session:
        first = seed_admin(session, "admin", "admin-pass")
        assert first is not None and first.role == "admin"
        second = seed_admin(session, "admin", "admin-pass")
        assert second is None
        assert get_user_by_username(session, "admin") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_auth_service.py -v`
Expected: FAIL (`ModuleNotFoundError: app.auth.schemas`).

- [ ] **Step 3: Implement schemas.py**

Create `backend/app/auth/schemas.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    display_name: str = ""
    role: str = "user"


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
```

- [ ] **Step 4: Implement service.py**

Create `backend/app/auth/service.py`:

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlmodel import Session, select

from app.auth.models import User
from app.auth.schemas import UserCreate
from app.auth.security import hash_password, verify_password


def get_user_by_username(session: Session, username: str) -> User | None:
    normalized = username.strip().lower()
    statement = select(User).where(func.lower(User.username) == normalized)
    return session.exec(statement).first()


def create_user(session: Session, data: UserCreate) -> User:
    if get_user_by_username(session, data.username) is not None:
        raise ValueError(f"Username already exists: {data.username}")
    user = User(
        username=data.username.strip(),
        display_name=(data.display_name or data.username).strip(),
        password_hash=hash_password(data.password),
        role=data.role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate(session: Session, username: str, password: str) -> User | None:
    user = get_user_by_username(session, username)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def seed_admin(session: Session, username: str, password: str) -> User | None:
    existing_admin = session.exec(select(User).where(User.role == "admin")).first()
    if existing_admin is not None:
        return None
    admin = User(
        username=username.strip(),
        display_name="Administrator",
        password_hash=hash_password(password),
        role="admin",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)
    return admin
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_auth_service.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/auth/schemas.py backend/app/auth/service.py backend/tests/test_auth_service.py
git commit -m "feat(auth): add auth schemas and user service"
```

---

### Task 5: Deps, router, route protection, admin seed on startup

**Files:**
- Create: `backend/app/auth/deps.py`
- Create: `backend/app/auth/router.py`
- Modify: `backend/app/main.py` (include auth router, protect data routers, seed admin on startup)
- Test: `backend/tests/test_auth_api.py`

**Interfaces:**
- Consumes: `get_session` (from `app.database`), `decode_access_token` (Task 3), `authenticate`/`create_user`/`get_user_by_username`/`seed_admin` (Task 4), schemas (Task 4).
- Produces deps: `get_current_user(...) -> User`, `require_admin(...) -> User`.
- Produces router at prefix `/api/auth`: `POST /login`, `GET /me`, `POST /users` (admin), `GET /users` (admin).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth_api.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

import app.main as main_module
from app.auth.schemas import UserCreate
from app.auth.service import create_user, seed_admin
from app.database import get_session


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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
```

Note: if `/api/health` path differs, check `app/routers/health.py` and adjust the assertion in `test_health_stays_open` to the actual health path.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_auth_api.py -v`
Expected: FAIL (`ModuleNotFoundError: app.auth.deps`).

- [ ] **Step 3: Implement deps.py**

Create `backend/app/auth/deps.py`:

```python
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.auth.models import User
from app.auth.security import decode_access_token
from app.auth.service import get_user_by_username
from app.database import get_session

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    username = decode_access_token(credentials.credentials)
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = get_user_by_username(session, username)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user
```

- [ ] **Step 4: Implement router.py**

Create `backend/app/auth/router.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.auth.deps import get_current_user, require_admin
from app.auth.models import User
from app.auth.schemas import LoginRequest, TokenResponse, UserCreate, UserOut
from app.auth.security import create_access_token
from app.auth.service import authenticate, create_user
from app.database import get_session

router = APIRouter()


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)):
    user = authenticate(session, body.username, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        )
    token = create_access_token(user.username)
    return TokenResponse(access_token=token, user=_to_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _to_out(user)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user_endpoint(
    body: UserCreate,
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    try:
        created = create_user(session, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_out(created)


@router.get("/users", response_model=list[UserOut])
def list_users_endpoint(
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    users = session.exec(select(User).order_by(User.id)).all()
    return [_to_out(u) for u in users]
```

- [ ] **Step 5: Wire router, protect data routes, seed admin**

Edit `backend/app/main.py`. Add imports near the other router imports:

```python
from app.auth.router import router as auth_router
from app.auth.deps import get_current_user
from fastapi import Depends
```

Replace the `include_router` block so data routers gain the auth dependency and the auth router is registered (health + auth stay open):

```python
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

_auth = [Depends(get_current_user)]
app.include_router(applications_router, prefix="/api/applications", dependencies=_auth)
app.include_router(status_router, prefix="/api/status", dependencies=_auth)
app.include_router(trademark_router, prefix="/api/tm-applications", dependencies=_auth)
app.include_router(tm_status_router, prefix="/api/tm-status", dependencies=_auth)
app.include_router(patents_router, prefix="/api/patents", dependencies=_auth)
app.include_router(us_pto_router, prefix="/api/us-pto", tags=["us-pto"], dependencies=_auth)
```

Update the startup handler to seed the admin after migrations:

```python
@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)
    run_schema_migrations()
    _seed_admin_on_startup()


def _seed_admin_on_startup() -> None:
    from sqlmodel import Session

    from app.auth.service import seed_admin
    from app.core.config import settings

    username = settings.AUTH_ADMIN_USERNAME
    password = settings.AUTH_ADMIN_PASSWORD
    if not username or not password:
        if settings.DEBUG:
            return
        raise RuntimeError("AUTH_ADMIN_USERNAME and AUTH_ADMIN_PASSWORD must be set")
    if not settings.DEBUG and settings.SECRET_KEY == "dev-insecure-change-me":
        raise RuntimeError("SECRET_KEY must be set to a non-default value in production")
    with Session(engine) as session:
        seed_admin(session, username, password)
```

- [ ] **Step 6: Run the auth API tests**

Run: `cd backend && pytest tests/test_auth_api.py -v`
Expected: PASS (6 tests). If `test_health_stays_open` fails, confirm the real health route in `app/routers/health.py` and adjust the path.

- [ ] **Step 7: Run the full backend suite**

Run: `cd backend && pytest -q`
Expected: all pass (new auth tests + existing suite).

- [ ] **Step 8: Commit**

```bash
git add backend/app/auth/deps.py backend/app/auth/router.py backend/app/main.py backend/tests/test_auth_api.py
git commit -m "feat(auth): add auth router, protect data routes, seed admin on startup"
```

---

### Task 6: Frontend — real AuthService, interceptor, routing

**Files:**
- Rewrite: `frontend/src/app/auth/auth.service.ts`
- Create: `frontend/src/app/auth/auth.interceptor.ts`
- Modify: `frontend/src/app/app.config.ts` (register interceptor)
- Modify: `frontend/src/app/app.routes.ts` (remove signup route + import)
- Modify: `frontend/src/app/auth/login.component.ts` (async login against backend)
- Delete: `frontend/src/app/auth/signup.component.ts` + `signup.component.html`
- Rewrite: `frontend/src/app/auth/auth.service.spec.ts`
- Create: `frontend/src/app/auth/auth.interceptor.spec.ts`

**Interfaces:**
- Consumes backend: `POST /api/auth/login` → `{access_token, token_type, user:{id,username,display_name,role,is_active}}`.
- Produces `AuthService`: `login(username, password): Observable<boolean>`, `logout(): void`, `token(): string | null`, signals `isAuthenticated`, `userDisplayName`.
- Produces `authInterceptor: HttpInterceptorFn`.

- [ ] **Step 1: Write the failing service spec**

Rewrite `frontend/src/app/auth/auth.service.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { environment } from '@env';
import { AuthService } from './auth.service';

describe('AuthService', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()]
    });
    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('logs in and stores the token', () => {
    let result: boolean | undefined;
    service.login('admin', 'admin-pass').subscribe((ok) => (result = ok));

    const req = httpMock.expectOne(`${environment.apiBaseUrl}/api/auth/login`);
    expect(req.request.method).toBe('POST');
    req.flush({
      access_token: 'tok123',
      token_type: 'bearer',
      user: { id: 1, username: 'admin', display_name: 'Administrator', role: 'admin', is_active: true }
    });

    expect(result).toBe(true);
    expect(service.isAuthenticated()).toBe(true);
    expect(service.token()).toBe('tok123');
    expect(service.userDisplayName()).toBe('Administrator');
  });

  it('logout clears the token', () => {
    service.login('admin', 'admin-pass').subscribe();
    httpMock.expectOne(`${environment.apiBaseUrl}/api/auth/login`).flush({
      access_token: 'tok123',
      token_type: 'bearer',
      user: { id: 1, username: 'admin', display_name: 'Administrator', role: 'admin', is_active: true }
    });

    service.logout();
    expect(service.isAuthenticated()).toBe(false);
    expect(service.token()).toBeNull();
  });
});
```

- [ ] **Step 2: Run spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include='**/auth.service.spec.ts'`
Expected: FAIL (compile error — old `AuthService` has no `token()` and `login` returns boolean).

- [ ] **Step 3: Rewrite auth.service.ts**

Replace `frontend/src/app/auth/auth.service.ts`:

```typescript
import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, map, of } from 'rxjs';
import { catchError, tap } from 'rxjs/operators';
import { environment } from '@env';

interface AuthUser {
  id: number;
  username: string;
  display_name: string;
  role: string;
  is_active: boolean;
}

interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

const TOKEN_KEY = 'patsync.auth.token';
const USER_KEY = 'patsync.auth.user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiBaseUrl}/api/auth`;

  private readonly tokenSig = signal<string | null>(localStorage.getItem(TOKEN_KEY));
  private readonly userSig = signal<AuthUser | null>(this.loadUser());

  readonly isAuthenticated = computed(() => this.tokenSig() !== null);
  readonly userDisplayName = computed(() => this.userSig()?.display_name ?? 'User');

  token(): string | null {
    return this.tokenSig();
  }

  login(username: string, password: string): Observable<boolean> {
    return this.http.post<LoginResponse>(`${this.baseUrl}/login`, { username, password }).pipe(
      tap((res) => this.persist(res)),
      map(() => true),
      catchError(() => of(false))
    );
  }

  logout(): void {
    this.tokenSig.set(null);
    this.userSig.set(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  private persist(res: LoginResponse): void {
    this.tokenSig.set(res.access_token);
    this.userSig.set(res.user);
    localStorage.setItem(TOKEN_KEY, res.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
  }

  private loadUser(): AuthUser | null {
    try {
      const raw = localStorage.getItem(USER_KEY);
      return raw ? (JSON.parse(raw) as AuthUser) : null;
    } catch {
      return null;
    }
  }
}
```

- [ ] **Step 4: Run service spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include='**/auth.service.spec.ts'`
Expected: PASS

- [ ] **Step 5: Write the interceptor spec**

Create `frontend/src/app/auth/auth.interceptor.spec.ts`:

```typescript
import { TestBed } from '@angular/core/testing';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Router } from '@angular/router';
import { environment } from '@env';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let auth: AuthService;
  let router: Router;

  beforeEach(() => {
    localStorage.setItem('patsync.auth.token', 'tok123');
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        { provide: Router, useValue: { navigateByUrl: jasmine.createSpy('navigateByUrl') } }
      ]
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
    router = TestBed.inject(Router);
  });

  afterEach(() => httpMock.verify());

  it('attaches the bearer token', () => {
    http.get(`${environment.apiBaseUrl}/api/status/`).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/api/status/`);
    expect(req.request.headers.get('Authorization')).toBe('Bearer tok123');
    req.flush([]);
  });

  it('logs out and redirects on 401', () => {
    spyOn(auth, 'logout').and.callThrough();
    http.get(`${environment.apiBaseUrl}/api/status/`).subscribe({ next: () => {}, error: () => {} });
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/api/status/`);
    req.flush({ detail: 'nope' }, { status: 401, statusText: 'Unauthorized' });
    expect(auth.logout).toHaveBeenCalled();
    expect(router.navigateByUrl).toHaveBeenCalledWith('/login');
  });
});
```

- [ ] **Step 6: Run interceptor spec to verify it fails**

Run: `cd frontend && npx ng test --watch=false --include='**/auth.interceptor.spec.ts'`
Expected: FAIL (`authInterceptor` not found).

- [ ] **Step 7: Implement the interceptor**

Create `frontend/src/app/auth/auth.interceptor.ts`:

```typescript
import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { AuthService } from './auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const token = auth.token();

  const authReq = token
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;

  return next(authReq).pipe(
    catchError((error) => {
      if (error?.status === 401) {
        auth.logout();
        router.navigateByUrl('/login');
      }
      return throwError(() => error);
    })
  );
};
```

- [ ] **Step 8: Register the interceptor**

Edit `frontend/src/app/app.config.ts`:

```typescript
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { routes } from './app.routes';
import { authInterceptor } from './auth/auth.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideRouter(routes)
  ]
};
```

- [ ] **Step 9: Run interceptor spec to verify it passes**

Run: `cd frontend && npx ng test --watch=false --include='**/auth.interceptor.spec.ts'`
Expected: PASS

- [ ] **Step 10: Update login.component.ts (async login)**

Replace the `login()` method and imports in `frontend/src/app/auth/login.component.ts`. Remove the `credentials`/`getDefaultCredentials` usage:

```typescript
import { CommonModule } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from './auth.service';

@Component({
  selector: 'app-login',
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.css'
})
export class LoginComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly submitError = signal('');
  protected readonly submitting = signal(false);

  protected readonly form = this.fb.group({
    username: ['', Validators.required],
    password: ['', Validators.required]
  });

  protected login(): void {
    this.submitError.set('');
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const username = this.form.controls.username.value ?? '';
    const password = this.form.controls.password.value ?? '';
    this.submitting.set(true);
    this.auth.login(username, password).subscribe((ok) => {
      this.submitting.set(false);
      if (!ok) {
        this.submitError.set('Invalid username or password.');
        return;
      }
      void this.router.navigate(['/dashboard']);
    });
  }
}
```

If `login.component.html` references `credentials` (default-credential hint), remove that markup block so the template compiles.

- [ ] **Step 11: Remove the signup page and route**

Delete `frontend/src/app/auth/signup.component.ts` and `frontend/src/app/auth/signup.component.html`.

In `frontend/src/app/app.routes.ts`, remove the `SignupComponent` import and the route line:

```typescript
  { path: 'signup', component: SignupComponent, canActivate: [guestGuard] },
```

Also remove any "Create account" `routerLink="/signup"` link in `login.component.html` if present (so no dead link remains).

- [ ] **Step 12: Run the full frontend test suite + build**

Run: `cd frontend && npx ng test --watch=false && npx ng build`
Expected: all specs PASS; build succeeds with no reference to `SignupComponent` or old `AuthService` API.

- [ ] **Step 13: Commit**

```bash
git add frontend/src/app/auth frontend/src/app/app.config.ts frontend/src/app/app.routes.ts
git rm frontend/src/app/auth/signup.component.ts frontend/src/app/auth/signup.component.html
git commit -m "feat(auth): wire frontend to backend auth, add bearer interceptor, remove signup"
```

---

### Task 7: Env docs

**Files:**
- Modify: `backend/.env.example`

**Interfaces:** none (documentation only).

- [ ] **Step 1: Document the new env vars**

Append to `backend/.env.example`:

```dotenv
# Auth
SECRET_KEY=change-me-to-a-long-random-string
ACCESS_TOKEN_EXPIRE_MINUTES=480
AUTH_ADMIN_USERNAME=admin
AUTH_ADMIN_PASSWORD=change-me
```

- [ ] **Step 2: Commit**

```bash
git add backend/.env.example
git commit -m "docs(auth): document auth env vars"
```

---

## Final Verification

- [ ] Run backend suite: `cd backend && pytest -q` — all pass.
- [ ] Run frontend suite: `cd frontend && npx ng test --watch=false` — all pass.
- [ ] Manual smoke: start backend with `SECRET_KEY` + `AUTH_ADMIN_*` set, `POST /api/auth/login` returns a token, `GET /api/status/` returns 401 without token and 200 with it.
- [ ] Push branch and open PR against `main`.
