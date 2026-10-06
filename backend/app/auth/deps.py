from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.auth.models import User
from app.auth.security import decode_access_token
from app.auth.service import get_user_by_username
from app.database import get_session

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    # Deliberately async def, not def: FastAPI dispatches each *sync*
    # dependency through its own threadpool hop (a fresh copy of the
    # request's contextvars per call), so set_actor() below would mutate a
    # throwaway copy that never reaches the mutating endpoint's own thread -
    # every audit row written during that request would see an empty actor.
    # An async dependency runs inline on the same task as the rest of the
    # request, so the actor it sets is visible to whatever thread the sync
    # endpoint body eventually (correctly) gets dispatched to.
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    username = decode_access_token(credentials.credentials)
    if username is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = get_user_by_username(session, username)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    from app.audit.context import set_actor
    set_actor(user.id, user.username)
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user
