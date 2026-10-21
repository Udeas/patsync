"""app.us_pto.auth.calendar's own branching logic (needs-auth / reuse-valid /
refresh-and-persist / exchange-and-persist) - the Google SDK classes
(Credentials, Flow, build) are patched per-test since conftest.py stubs the
whole google-auth stack as blanket MagicMocks (ABI-broken in this venv), so
only an explicitly-configured fake behaves predictably."""

from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import SQLModel

from app.database import engine
from app.us_pto.auth import calendar as calendar_auth
from app.us_pto.auth.token_store import (
    NeedsAuthorizationError,
    load_token_json,
    save_pkce_verifier,
    save_token_json,
)
from app.us_pto.models import GoogleOAuthToken, OAuthPkceVerifier  # noqa: F401


def setup_function() -> None:
    SQLModel.metadata.create_all(engine)


def test_raises_needs_authorization_when_no_token_stored() -> None:
    with pytest.raises(NeedsAuthorizationError):
        calendar_auth.get_calendar_service()


def test_reuses_valid_credentials_without_refreshing() -> None:
    save_token_json(calendar_auth.PROVIDER, '{"token": "still-good"}')
    fake_creds = MagicMock(valid=True)

    with patch.object(calendar_auth.Credentials, "from_authorized_user_info", return_value=fake_creds):
        with patch.object(calendar_auth, "build") as fake_build:
            calendar_auth.get_calendar_service()

    fake_creds.refresh.assert_not_called()
    fake_build.assert_called_once_with("calendar", "v3", credentials=fake_creds)


def test_refreshes_and_persists_expired_credentials_with_refresh_token() -> None:
    save_token_json(calendar_auth.PROVIDER, '{"token": "expired"}')
    fake_creds = MagicMock(valid=False, expired=True, refresh_token="rt")
    fake_creds.to_json.return_value = '{"token": "refreshed"}'

    with patch.object(calendar_auth.Credentials, "from_authorized_user_info", return_value=fake_creds):
        with patch.object(calendar_auth, "build") as fake_build:
            calendar_auth.get_calendar_service()

    fake_creds.refresh.assert_called_once()
    assert load_token_json(calendar_auth.PROVIDER) == '{"token": "refreshed"}'
    fake_build.assert_called_once_with("calendar", "v3", credentials=fake_creds)


def test_raises_needs_authorization_when_invalid_and_no_refresh_token() -> None:
    save_token_json(calendar_auth.PROVIDER, '{"token": "dead"}')
    fake_creds = MagicMock(valid=False, expired=True, refresh_token=None)

    with patch.object(calendar_auth.Credentials, "from_authorized_user_info", return_value=fake_creds):
        with pytest.raises(NeedsAuthorizationError):
            calendar_auth.get_calendar_service()


def test_exchange_code_persists_credentials_from_flow() -> None:
    save_pkce_verifier("state123", "saved-verifier")
    fake_flow = MagicMock()
    fake_flow.credentials.to_json.return_value = '{"token": "exchanged"}'

    with patch.object(calendar_auth.Flow, "from_client_secrets_file", return_value=fake_flow) as from_secrets:
        calendar_auth.exchange_code("the-code", "https://example.com/callback", "state123")

    fake_flow.fetch_token.assert_called_once_with(code="the-code")
    from_secrets.assert_called_once_with(
        calendar_auth.GOOGLE_CREDS_FILE,
        scopes=calendar_auth.CALENDAR_SCOPES,
        redirect_uri="https://example.com/callback",
        code_verifier="saved-verifier",
    )
    assert load_token_json(calendar_auth.PROVIDER) == '{"token": "exchanged"}'


def test_exchange_code_raises_when_state_has_no_saved_verifier() -> None:
    with pytest.raises(ValueError, match="state"):
        calendar_auth.exchange_code("the-code", "https://example.com/callback", "never-saved-state")


def test_build_authorize_url_returns_flow_url_and_persists_verifier() -> None:
    fake_flow = MagicMock(code_verifier="the-verifier")
    fake_flow.authorization_url.return_value = ("https://accounts.google.com/auth?...", "state123")

    with patch.object(calendar_auth.Flow, "from_client_secrets_file", return_value=fake_flow):
        url = calendar_auth.build_authorize_url("https://example.com/callback")

    assert url == "https://accounts.google.com/auth?..."
    from app.us_pto.auth.token_store import pop_pkce_verifier

    assert pop_pkce_verifier("state123") == "the-verifier"
