"""Registration, login, logout and current-user endpoints.

The signed session cookie stores the user's ID and last authenticated activity.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from math import isfinite
from time import time

from backend.database import repository
from backend.database.connection import session_scope
from backend.models import User
from backend.services import auth_service

MIN_PASSWORD_LENGTH = 8
SESSION_IDLE_SECONDS = 5 * 60

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str = ""
    password: str = ""


def _public_user(user: User) -> dict:
    return {"id": user.id, "email": user.email}


def get_current_user(request: Request) -> User:
    """Dependency: the logged-in user, or 401."""
    user_id = request.session.get("user_id")
    last_activity = request.session.get("last_activity")
    now = time()
    if (
        type(last_activity) not in (int, float)
        or not isfinite(last_activity)
        or not 0 <= now - last_activity < SESSION_IDLE_SECONDS
    ):
        request.session.clear()
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    user = None
    if user_id is not None:
        with session_scope(request.app.state.engine) as session:
            user = repository.get_user(session, user_id)
    if user is None:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Not authenticated.")
    request.session["last_activity"] = now
    return user


@router.post("/register", status_code=201)
def register(credentials: Credentials, request: Request) -> dict:
    email = auth_service.normalize_email(credentials.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email is required.")
    if len(credentials.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )

    duplicate = HTTPException(
        status_code=409, detail="An account with this email already exists."
    )
    try:
        with session_scope(request.app.state.engine) as session:
            if repository.get_user_by_email(session, email) is not None:
                raise duplicate
            user = repository.create_user(
                session,
                email=email,
                password_hash=auth_service.hash_password(credentials.password),
            )
    except IntegrityError:
        raise duplicate

    request.session["user_id"] = user.id
    request.session["last_activity"] = time()
    return _public_user(user)


@router.post("/login")
def login(credentials: Credentials, request: Request) -> dict:
    with session_scope(request.app.state.engine) as session:
        user = auth_service.authenticate_user(
            session, credentials.email, credentials.password
        )
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["last_activity"] = time()
    return _public_user(user)


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"status": "logged_out"}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return _public_user(user)
