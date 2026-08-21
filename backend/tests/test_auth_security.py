import time

from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_roundtrip() -> None:
    hashed = hash_password("secret12")
    assert hashed != "secret12"
    assert verify_password("secret12", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_token_roundtrip() -> None:
    token = create_access_token("admin")
    assert decode_access_token(token) == "admin"


def test_token_garbage_returns_none() -> None:
    assert decode_access_token("not.a.token") is None


def test_token_expired_returns_none() -> None:
    token = create_access_token("admin", expires_minutes=-1)
    time.sleep(0.01)
    assert decode_access_token(token) is None
