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
