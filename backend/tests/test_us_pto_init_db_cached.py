"""init_db() must run schema migrations at most once per process - it's
called before nearly every us_pto repository operation (including once per
row inserted), and re-running the full migration DDL every time caused
severe per-row overhead and could hang indefinitely under lock contention."""

from unittest.mock import MagicMock, patch

from app.us_pto import repository


def test_init_db_only_runs_migrations_once(monkeypatch):
    monkeypatch.setattr(repository, "_db_initialized", False)
    mock_migrations = MagicMock()

    with patch("app.database.run_schema_migrations", mock_migrations):
        repository.init_db()
        repository.init_db()
        repository.init_db()

    mock_migrations.assert_called_once()
