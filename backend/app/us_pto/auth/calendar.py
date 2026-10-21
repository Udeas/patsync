import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.us_pto.auth.token_store import (
    NeedsAuthorizationError,
    load_token_json,
    pop_pkce_verifier,
    save_pkce_verifier,
    save_token_json,
)
from app.us_pto.config import CALENDAR_SCOPES, GOOGLE_CREDS_FILE

PROVIDER = "calendar"


def _load_credentials() -> Credentials | None:
    token_json = load_token_json(PROVIDER)
    if not token_json:
        return None
    return Credentials.from_authorized_user_info(json.loads(token_json), CALENDAR_SCOPES)


def get_calendar_service():
    creds = _load_credentials()
    if creds and not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_token_json(PROVIDER, creds.to_json())
    elif not creds or not creds.valid:
        raise NeedsAuthorizationError(PROVIDER)
    return build("calendar", "v3", credentials=creds)


def build_authorize_url(redirect_uri: str) -> str:
    flow = Flow.from_client_secrets_file(GOOGLE_CREDS_FILE, scopes=CALENDAR_SCOPES, redirect_uri=redirect_uri)
    auth_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    save_pkce_verifier(state, flow.code_verifier)
    return auth_url


def exchange_code(code: str, redirect_uri: str, state: str) -> None:
    code_verifier = pop_pkce_verifier(state)
    if not code_verifier:
        raise ValueError(f"no PKCE verifier found for state {state!r} - authorize again")
    flow = Flow.from_client_secrets_file(
        GOOGLE_CREDS_FILE, scopes=CALENDAR_SCOPES, redirect_uri=redirect_uri, code_verifier=code_verifier
    )
    flow.fetch_token(code=code)
    save_token_json(PROVIDER, flow.credentials.to_json())
