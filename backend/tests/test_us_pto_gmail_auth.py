"""Mirrors test_us_pto_calendar_auth.py for app.us_pto.auth.gmail - same
branching logic, same reasons for mocking the Google SDK classes per-test."""

from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import SQLModel

from app.database import engine
from app.us_pto.auth import gmail as gmail_auth
from app.us_pto.auth.token_store import NeedsAuthorizationError, load_token_json, save_token_json
from app.us_pto.models import GoogleOAuthToken  # noqa: F401


def setup_function() -> None:
    SQLModel.metadata.create_all(engine)


def test_raises_needs_authorization_when_no_token_stored() -> None:
    with pytest.raises(NeedsAuthorizationError):
        gmail_auth.get_gmail_service()


def test_reuses_valid_credentials_without_refreshing() -> None:
    save_token_json(gmail_auth.PROVIDER, '{"token": "still-good"}')
    fake_creds = MagicMock(valid=True)

    with patch.object(gmail_auth.Credentials, "from_authorized_user_info", return_value=fake_creds):
        with patch.object(gmail_auth, "build") as fake_build:
            gmail_auth.get_gmail_service()

    fake_creds.refresh.assert_not_called()
    fake_build.assert_called_once_with("gmail", "v1", credentials=fake_creds)


def test_refreshes_and_persists_expired_credentials_with_refresh_token() -> None:
    save_token_json(gmail_auth.PROVIDER, '{"token": "expired"}')
    fake_creds = MagicMock(valid=False, expired=True, refresh_token="rt")
    fake_creds.to_json.return_value = '{"token": "refreshed"}'

    with patch.object(gmail_auth.Credentials, "from_authorized_user_info", return_value=fake_creds):
        with patch.object(gmail_auth, "build") as fake_build:
            gmail_auth.get_gmail_service()

    fake_creds.refresh.assert_called_once()
    assert load_token_json(gmail_auth.PROVIDER) == '{"token": "refreshed"}'
    fake_build.assert_called_once_with("gmail", "v1", credentials=fake_creds)


def test_raises_needs_authorization_when_invalid_and_no_refresh_token() -> None:
    save_token_json(gmail_auth.PROVIDER, '{"token": "dead"}')
    fake_creds = MagicMock(valid=False, expired=True, refresh_token=None)

    with patch.object(gmail_auth.Credentials, "from_authorized_user_info", return_value=fake_creds):
        with pytest.raises(NeedsAuthorizationError):
            gmail_auth.get_gmail_service()


def test_exchange_code_persists_credentials_from_flow() -> None:
    fake_flow = MagicMock()
    fake_flow.credentials.to_json.return_value = '{"token": "exchanged"}'

    with patch.object(gmail_auth.Flow, "from_client_secrets_file", return_value=fake_flow) as from_secrets:
        gmail_auth.exchange_code("the-code", "https://example.com/callback")

    fake_flow.fetch_token.assert_called_once_with(code="the-code")
    from_secrets.assert_called_once_with(
        gmail_auth.GOOGLE_CREDS_FILE,
        scopes=gmail_auth.GMAIL_SCOPES,
        redirect_uri="https://example.com/callback",
    )
    assert load_token_json(gmail_auth.PROVIDER) == '{"token": "exchanged"}'


def test_build_authorize_url_returns_flow_url() -> None:
    fake_flow = MagicMock()
    fake_flow.authorization_url.return_value = ("https://accounts.google.com/auth?...", "state123")

    with patch.object(gmail_auth.Flow, "from_client_secrets_file", return_value=fake_flow):
        url = gmail_auth.build_authorize_url("https://example.com/callback")

    assert url == "https://accounts.google.com/auth?..."
