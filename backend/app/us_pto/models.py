from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class UsptoTracker(SQLModel, table=True):
    __tablename__ = "uspto_tracker"

    id: Optional[int] = Field(default=None, primary_key=True)
    docket_no: str = Field(max_length=64)
    application_no: str = Field(default="", max_length=32)
    doc_code: str = Field(max_length=32)
    particulars: str = Field(default="")
    event_date: str = Field(max_length=16)
    final_due_date: Optional[date] = None
    work_status: str = Field(default="Pending", max_length=32)
    completion_date: Optional[date] = None
    comment: str = Field(default="")
    calendar_event_ids: str = Field(default="")
    calendar_status: str = Field(default="", max_length=64)
    template_status: str = Field(default="", max_length=64)
    is_closure_done: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class GoogleOAuthToken(SQLModel, table=True):
    __tablename__ = "google_oauth_token"

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(max_length=32, unique=True, index=True)
    token_json: str = Field(default="")
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OAuthPkceVerifier(SQLModel, table=True):
    """The PKCE code_verifier google-auth-oauthlib's Flow auto-generates when
    building the authorize URL, keyed by the OAuth `state` param so the
    callback - a separate request, with its own fresh Flow instance - can
    retrieve the matching verifier before exchanging the code. Single-use:
    popped (read + deleted) on success."""

    __tablename__ = "oauth_pkce_verifier"

    id: Optional[int] = Field(default=None, primary_key=True)
    state: str = Field(max_length=128, unique=True, index=True)
    code_verifier: str = Field(max_length=256)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DocCodeRule(SQLModel, table=True):
    __tablename__ = "doc_code_rules"

    id: Optional[int] = Field(default=None, primary_key=True)
    doc_code: str = Field(max_length=32, unique=True, index=True)
    final_due_months: int
    final_due_extension_months: int
    email_template: Optional[str] = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
