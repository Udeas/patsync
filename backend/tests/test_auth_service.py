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
