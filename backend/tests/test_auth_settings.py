import importlib


def test_settings_expose_auth_fields(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret")
    import app.core.config as config
    importlib.reload(config)
    s = config.Settings()
    assert s.SECRET_KEY == "unit-test-secret"
    assert s.ALGORITHM == "HS256"
    assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 480
    assert s.AUTH_ADMIN_USERNAME is None
