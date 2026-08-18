from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.auth.deps import get_current_user, require_admin
from app.auth.models import User
from app.auth.schemas import LoginRequest, TokenResponse, UserCreate, UserOut
from app.auth.security import create_access_token
from app.auth.service import authenticate, create_user
from app.database import get_session

router = APIRouter()


def _to_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)):
    user = authenticate(session, body.username, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        )
    token = create_access_token(user.username)
    return TokenResponse(access_token=token, user=_to_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _to_out(user)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user_endpoint(
    body: UserCreate,
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    try:
        created = create_user(session, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_out(created)


@router.get("/users", response_model=list[UserOut])
def list_users_endpoint(
    _admin: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    users = session.exec(select(User).order_by(User.id)).all()
    return [_to_out(u) for u in users]
