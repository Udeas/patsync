from __future__ import annotations

from sqlmodel import Session

from app.database import engine


def get_us_pto_engine():
    return engine


def get_us_pto_session():
    with Session(get_us_pto_engine()) as session:
        yield session
