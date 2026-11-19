"""Verified accounts and server-revocable login sessions."""
import hmac
import re
import secrets
from math import isfinite
from time import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from backend.database import repository
from backend.database.connection import session_scope
from backend.models import User
from backend.models.account_security import AccountVerification, LoginSession, VerificationChallenge
from backend.services import auth_service, account_security as security
from backend.services.showcase import EMAIL

MIN_PASSWORD_LENGTH = 15
SESSION_IDLE_SECONDS = 5 * 60
router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str = Field(default="", max_length=254)
    password: str = Field(default="", max_length=1024)


class VerificationCode(BaseModel):
    code: str = Field(pattern=r"^[0-9]{8}$")


def _public_user(user: User) -> dict:
    return {"id": user.id, "email": user.email}


def get_current_user(request: Request) -> User:
    """Single access boundary for app APIs: valid session AND verified email."""
    last_activity = request.session.get("last_activity")
    now = time()
    if (type(last_activity) not in (int, float) or not isfinite(last_activity)
            or not 0 <= now - last_activity < SESSION_IDLE_SECONDS):
        if "verification_challenge" not in request.session:
            request.session.clear()
        raise HTTPException(401, "Session expired. Please sign in again.")
    token = request.session.get("token")
    user = None
    with session_scope(request.app.state.engine) as session:
        login = session.get(LoginSession, security.digest(token)) if isinstance(token, str) else None
        if login and login.expires_at > now and login.absolute_expires_at > now:
            verification = session.get(AccountVerification, login.user_id)
            if verification and verification.verified_at is not None:
                user = repository.get_user(session, login.user_id)
                if user and user.email != EMAIL:
                    login.expires_at = min(now + SESSION_IDLE_SECONDS, login.absolute_expires_at)
                else:
                    user = None
    if user is None:
        request.session.clear()
        raise HTTPException(401, "Sign in and verify your email to continue.")
    request.session["last_activity"] = now
    return user


def _begin_verification(request: Request, user: User) -> dict:
    now = time()
    security.limit(request, "verification-email", str(user.id), 3, now)
    security.revoke_session(request)
    challenge_id, code = secrets.token_urlsafe(32), f"{secrets.randbelow(100000000):08d}"
    with session_scope(request.app.state.engine) as session:
        session.execute(delete(VerificationChallenge).where(
            (VerificationChallenge.user_id == user.id) | (VerificationChallenge.expires_at <= now)))
        session.add(VerificationChallenge(id=challenge_id, user_id=user.id,
            code_hash=security.code_digest(request.app.state.session_signing_key, challenge_id, code),
            expires_at=now + security.CHALLENGE_SECONDS, attempts=0))
    request.session["verification_challenge"] = challenge_id
    try:
        security.send_verification_email(user.email, code)
    except Exception:
        # Keep pending browser state so resend can recover delivery failures.
        # Never expose SMTP credentials, recipient data, or verification codes.
        raise HTTPException(503, "Verification email could not be sent. Try resending shortly or contact the site owner.")
    return {"verification_required": True}


@router.post("/register", status_code=201)
def register(credentials: Credentials, request: Request) -> dict:
    email = auth_service.normalize_email(credentials.email)
    security.limit_auth(request, email, time())
    if email == EMAIL or not re.fullmatch(
        r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
        r"(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+", email
    ):
        raise HTTPException(400, "A valid email is required.")
    if len(credentials.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    duplicate = HTTPException(409, "Unable to create this account. Try signing in instead.")
    try:
        with session_scope(request.app.state.engine) as session:
            if repository.get_user_by_email(session, email) is not None:
                raise duplicate
            user = repository.create_user(session, email=email,
                                           password_hash=auth_service.hash_password(credentials.password))
    except IntegrityError:
        raise duplicate
    return _begin_verification(request, user)


@router.post("/login")
def login(credentials: Credentials, request: Request) -> dict:
    email = auth_service.normalize_email(credentials.email)
    security.limit_auth(request, email, time())
    with session_scope(request.app.state.engine) as session:
        user = auth_service.authenticate_user(session, email, credentials.password)
        verified = session.get(AccountVerification, user.id) if user else None
        verified = verified is not None and verified.verified_at is not None
    if user is None or user.email == EMAIL:
        raise HTTPException(401, "Invalid email or password.")
    if not verified:
        return _begin_verification(request, user)
    security.revoke_session(request)
    with session_scope(request.app.state.engine) as session:
        security.start_session(request, session, user.id, time(), SESSION_IDLE_SECONDS)
    return _public_user(user)


@router.post("/verify-email")
def verify_email(payload: VerificationCode, request: Request) -> dict:
    now = time()
    security.limit(request, "verify-ip", request.client.host if request.client else "unknown", 30, now)
    challenge_id = request.session.get("verification_challenge")
    if not isinstance(challenge_id, str):
        raise HTTPException(400, "Start verification by signing in first.")
    user = None
    with session_scope(request.app.state.engine) as session:
        # Conditional write serializes concurrent guesses and code consumption.
        challenge = session.execute(update(VerificationChallenge).where(
            VerificationChallenge.id == challenge_id,
            VerificationChallenge.expires_at > now,
            VerificationChallenge.attempts < security.MAX_CODE_ATTEMPTS,
        ).values(attempts=VerificationChallenge.attempts + 1).returning(VerificationChallenge)).scalar_one_or_none()
        candidate = security.code_digest(request.app.state.session_signing_key, challenge_id, payload.code)
        if challenge and hmac.compare_digest(challenge.code_hash, candidate):
            user = repository.get_user(session, challenge.user_id)
            verification = session.get(AccountVerification, user.id)
            if verification is None:
                session.add(AccountVerification(user_id=user.id, verified_at=now))
            else:
                verification.verified_at = now
            session.delete(challenge)
            security.start_session(request, session, user.id, now, SESSION_IDLE_SECONDS)
    if user is None:
        # Outside the transaction so failed attempts are committed.
        raise HTTPException(400, "Invalid or expired code. Request a new code if needed.")
    return _public_user(user)


@router.post("/resend-verification")
def resend_verification(request: Request) -> dict:
    security.limit(request, "resend-ip", request.client.host if request.client else "unknown", 10, time())
    challenge_id = request.session.get("verification_challenge")
    with session_scope(request.app.state.engine) as session:
        challenge = session.get(VerificationChallenge, challenge_id) if isinstance(challenge_id, str) else None
        user = repository.get_user(session, challenge.user_id) if challenge else None
    if user is None:
        raise HTTPException(400, "Sign in again to request a verification code.")
    return _begin_verification(request, user)


@router.post("/logout")
def logout(request: Request) -> dict:
    challenge_id = request.session.get("verification_challenge")
    if isinstance(challenge_id, str):
        with session_scope(request.app.state.engine) as session:
            session.execute(delete(VerificationChallenge).where(VerificationChallenge.id == challenge_id))
    security.revoke_session(request)
    return {"status": "logged_out"}


@router.post("/demo")
def demo() -> dict:
    raise HTTPException(403, "Demo login is disabled. Sign in with a verified account.")


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return _public_user(user)
