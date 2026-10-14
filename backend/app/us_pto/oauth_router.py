"""Google OAuth callback endpoints for the USPTO automation module.

Deliberately NOT mounted with the rest of us_pto.router's app-auth
dependency: Google's redirect back here is a plain top-level browser
navigation (the user clicking "Allow" on the consent screen), which never
carries our app's bearer token - it's a different kind of request from
every other call in this module, and would 401 before reaching the handler
if grouped under that same auth-protected router.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.us_pto.auth.calendar import exchange_code as exchange_calendar_code
from app.us_pto.auth.gmail import exchange_code as exchange_gmail_code
from app.us_pto.auth.oauth_redirect import calendar_redirect_uri, gmail_redirect_uri

router = APIRouter()

_SUCCESS_HTML = "<p>{label} authorized. You can close this tab and return to Patsync.</p>"
_FAILURE_HTML = "<p>{label} authorization failed: {error}. Close this tab and try again.</p>"


@router.get("/automation/step-2/oauth/callback")
def calendar_oauth_callback(request: Request, code: str = Query(...), state: str = Query(...)):
    try:
        exchange_calendar_code(code, calendar_redirect_uri(request), state)
    except Exception as exc:
        return HTMLResponse(_FAILURE_HTML.format(label="Calendar", error=exc), status_code=400)
    return HTMLResponse(_SUCCESS_HTML.format(label="Calendar"))


@router.get("/automation/step-3/oauth/callback")
def gmail_oauth_callback(request: Request, code: str = Query(...), state: str = Query(...)):
    try:
        exchange_gmail_code(code, gmail_redirect_uri(request), state)
    except Exception as exc:
        return HTMLResponse(_FAILURE_HTML.format(label="Gmail", error=exc), status_code=400)
    return HTMLResponse(_SUCCESS_HTML.format(label="Gmail"))
