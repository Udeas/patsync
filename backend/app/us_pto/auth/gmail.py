import os

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.us_pto.config import GMAIL_DRAFTS_TOKEN_FILE, GMAIL_SCOPES, GOOGLE_CREDS_FILE


def get_gmail_service():
    creds = None
    if os.path.exists(GMAIL_DRAFTS_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(GMAIL_DRAFTS_TOKEN_FILE, GMAIL_SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDS_FILE, GMAIL_SCOPES)
        creds = flow.run_local_server(port=0)
        with open(GMAIL_DRAFTS_TOKEN_FILE, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)
