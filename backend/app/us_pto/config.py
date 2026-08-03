from __future__ import annotations

import os

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_REPO_ROOT = os.path.dirname(os.path.dirname(_BACKEND_ROOT))
_STEM_V2_ROOT = os.path.join(_REPO_ROOT, "stem-v2")


def _load_dotenv() -> None:
    for env_path in (
        os.path.join(_BACKEND_ROOT, ".env"),
        os.path.join(_STEM_V2_ROOT, ".env"),
    ):
        if not os.path.exists(env_path):
            continue
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path, override=False)
        except ImportError:
            pass


_load_dotenv()

CRED_DIR = os.environ.get("US_PTO_CRED_DIR", os.path.join(_STEM_V2_ROOT, "cred"))
DOC_CODES_CONFIG = os.environ.get(
    "US_PTO_DOC_CODES_PATH",
    os.path.join(_STEM_V2_ROOT, "config", "doc_codes.yaml"),
)
HTML_BACKUP_FILE = os.environ.get(
    "US_PTO_HTML_BACKUP_FILE",
    os.path.join(_STEM_V2_ROOT, "excel-data", "00_master_sheet_backup.html"),
)
SQLITE_SOURCE = os.environ.get(
    "US_PTO_SQLITE_SOURCE",
    os.path.join(_STEM_V2_ROOT, "stem.db"),
)

# Google Calendar ID used by Steps 2 and 4 (API). Set US_PTO_CALENDAR_ID in .env or below.
CALENDAR_ID = os.environ.get("US_PTO_CALENDAR_ID", os.environ.get("STEM_CALENDAR_ID", ""))
# Friendly label shown in the UI (Run Automation, View US Dockets). Set US_PTO_CALENDAR_DISPLAY_NAME in .env.
CALENDAR_DISPLAY_NAME = os.environ.get(
    "US_PTO_CALENDAR_DISPLAY_NAME",
    os.environ.get("STEM_CALENDAR_DISPLAY_NAME", "Test Calendar"),
)
CALENDAR_TOKEN_FILE = os.path.join(CRED_DIR, "token.json")
GMAIL_DRAFTS_TOKEN_FILE = os.path.join(CRED_DIR, "token_gmail_drafts.json")
GOOGLE_CREDS_FILE = os.path.join(CRED_DIR, "credentials.json")

IMAP_HOST = os.environ.get("US_PTO_IMAP_HOST", os.environ.get("STEM_IMAP_HOST", "imap.gmail.com"))
IMAP_USERNAME = os.environ.get("US_PTO_IMAP_USERNAME", os.environ.get("STEM_IMAP_USERNAME", ""))
IMAP_PASSWORD = os.environ.get("US_PTO_IMAP_PASSWORD", os.environ.get("STEM_IMAP_PASSWORD", ""))
IMAP_MAILBOX = os.environ.get("US_PTO_IMAP_MAILBOX", os.environ.get("STEM_IMAP_MAILBOX", "Tracker_Updates"))

CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar"]
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

WORK_STATUS_PENDING = "Pending"
WORK_STATUS_UNDER_EXTENSION = "Under Extension"
WORK_STATUS_DONE = "Done"
WORK_STATUS_CHOICES = [WORK_STATUS_PENDING, WORK_STATUS_UNDER_EXTENSION, WORK_STATUS_DONE]

CLOSURE_NOTE = "Future events marked Closed"
