"""Google OAuth token persistence for the USPTO automation module - DB-backed
(not a local file) so tokens survive Render redeploys, which wipe local disk."""

from sqlmodel import SQLModel

from app.database import engine
from app.us_pto.auth.token_store import load_token_json, pop_pkce_verifier, save_pkce_verifier, save_token_json
from app.us_pto.models import GoogleOAuthToken, OAuthPkceVerifier  # noqa: F401


def setup_function() -> None:
    SQLModel.metadata.create_all(engine)


def test_load_returns_none_when_no_token_stored() -> None:
    assert load_token_json("calendar-missing") is None


def test_save_then_load_round_trips() -> None:
    save_token_json("calendar-roundtrip", '{"token": "abc"}')

    assert load_token_json("calendar-roundtrip") == '{"token": "abc"}'


def test_save_upserts_existing_provider_row() -> None:
    save_token_json("calendar-upsert", '{"token": "first"}')
    save_token_json("calendar-upsert", '{"token": "second"}')

    assert load_token_json("calendar-upsert") == '{"token": "second"}'


def test_providers_are_independent() -> None:
    save_token_json("calendar-indep", '{"token": "cal"}')
    save_token_json("gmail-indep", '{"token": "gmail"}')

    assert load_token_json("calendar-indep") == '{"token": "cal"}'
    assert load_token_json("gmail-indep") == '{"token": "gmail"}'


def test_pop_pkce_verifier_returns_none_for_unknown_state() -> None:
    assert pop_pkce_verifier("unknown-state") is None


def test_pop_pkce_verifier_returns_saved_verifier() -> None:
    save_pkce_verifier("state-abc", "verifier-xyz")

    assert pop_pkce_verifier("state-abc") == "verifier-xyz"


def test_pop_pkce_verifier_is_single_use() -> None:
    save_pkce_verifier("state-once", "verifier-once")
    pop_pkce_verifier("state-once")

    assert pop_pkce_verifier("state-once") is None
