"""Persists Google OAuth tokens in Postgres instead of a local file.

Render's filesystem is ephemeral (wiped on every redeploy/restart), and the
credentials directory used in dev is outside the deployed `backend/` root
entirely - a locally-written token.json never survives either path on
Render. The DB is the one thing both environments share.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from app.us_pto.database import get_us_pto_engine
from app.us_pto.models import GoogleOAuthToken


class NeedsAuthorizationError(Exception):
    """No valid token on file for this provider - the admin must go through
    the authorize flow before the automation step can run."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"{provider} is not authorized yet")


def load_token_json(provider: str) -> str | None:
    with Session(get_us_pto_engine()) as session:
        row = session.exec(select(GoogleOAuthToken).where(GoogleOAuthToken.provider == provider)).first()
        return row.token_json if row else None


def save_token_json(provider: str, token_json: str) -> None:
    with Session(get_us_pto_engine()) as session:
        row = session.exec(select(GoogleOAuthToken).where(GoogleOAuthToken.provider == provider)).first()
        if row:
            row.token_json = token_json
            row.updated_at = datetime.utcnow()
        else:
            row = GoogleOAuthToken(provider=provider, token_json=token_json)
        session.add(row)
        session.commit()
