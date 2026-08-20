from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Text
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


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    actor_user_id: Optional[int] = Field(default=None, index=True)
    actor_username: Optional[str] = Field(default=None, max_length=64)
    action: str = Field(max_length=32, index=True)
    entity_type: Optional[str] = Field(default=None, max_length=32, index=True)
    entity_id: Optional[int] = Field(default=None)
    entity_label: Optional[str] = Field(default=None, max_length=255)
    changes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    ip_address: Optional[str] = Field(default=None, max_length=64)
