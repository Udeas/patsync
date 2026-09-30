# TEMPORARY ENV WORKAROUND — remove when the venv is rebuilt with Python 3.13 wheels.
# Stubs ABI-broken C extensions (psycopg2, google-auth) so app.main imports under tests.
#
# The venv's psycopg2 and google-auth C extensions are not loadable in this environment
# (Python 3.14 ABI mismatch). We stub them in sys.modules before any test module imports
# app.main. Using setdefault() ensures real modules take precedence on a healthy venv.
import os
import sys
from types import ModuleType
from unittest.mock import MagicMock

# 1. Override DATABASE_URL to SQLite so app.database doesn't try to
#    connect to PostgreSQL at module load time.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

# 2. Stub out psycopg2 (PostgreSQL C driver) and common submodules
#    so any `from psycopg2.extras import ...` / `.extensions` / `.pool` doesn't fail.
_psycopg2_mod = ModuleType("psycopg2")
sys.modules.setdefault("psycopg2", _psycopg2_mod)
sys.modules.setdefault("psycopg2._psycopg", MagicMock())
sys.modules.setdefault("psycopg2.extras", MagicMock())
sys.modules.setdefault("psycopg2.extensions", MagicMock())
sys.modules.setdefault("psycopg2.pool", MagicMock())

# 3. Stub out the full google.oauth2 / google.auth chain so that
#    app.us_pto.auth.calendar / gmail imports don't fail.
for _mod in [
    "google",
    "google.auth",
    "google.auth.crypt",
    "google.auth.crypt.es",
    "google.auth.crypt.rsa",
    "google.auth.jwt",
    "google.auth._helpers",
    "google.auth._service_account_info",
    "google.auth.credentials",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.oauth2",
    "google.oauth2.credentials",
    "google.oauth2.reauth",
    "google.oauth2._client",
    "google.oauth2.service_account",
    "googleapiclient",
    "googleapiclient.discovery",
    "googleapiclient.errors",
    "google_auth_oauthlib",
    "google_auth_oauthlib.flow",
]:
    sys.modules.setdefault(_mod, MagicMock())
