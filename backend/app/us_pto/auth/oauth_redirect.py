"""Shared redirect_uri builders for the Calendar/Gmail OAuth flow.

Used on both sides of the flow - building the authorize URL (router.py,
behind app auth) and handling Google's callback (oauth_router.py, public) -
so they must compute the identical value. Derived from the incoming
request's host rather than a hardcoded config value so it's correct in both
local dev and whatever the deployed domain happens to be; it must still
match a redirect URI whitelisted in the Google Cloud Console OAuth client.
"""

from __future__ import annotations

from fastapi import Request


def calendar_redirect_uri(request: Request) -> str:
    return f"{str(request.base_url).rstrip('/')}/api/us-pto/automation/step-2/oauth/callback"


def gmail_redirect_uri(request: Request) -> str:
    return f"{str(request.base_url).rstrip('/')}/api/us-pto/automation/step-3/oauth/callback"
