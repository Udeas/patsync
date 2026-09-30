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
