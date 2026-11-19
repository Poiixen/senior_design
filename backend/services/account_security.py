"""Authentication state stays in SQLite; cookies contain only opaque identifiers."""
import hashlib
import hmac
import os
import secrets
import smtplib
import ssl
from email.message import EmailMessage

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert

from backend.database.connection import session_scope
from backend.models.account_security import AuthRateBucket, LoginSession

CHALLENGE_SECONDS = 10 * 60
MAX_CODE_ATTEMPTS = 5
ABSOLUTE_SESSION_SECONDS = 12 * 60 * 60


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def code_digest(key: str, challenge: str, code: str) -> str:
    return hmac.new(key.encode(), f"{challenge}:{code}".encode(), hashlib.sha256).hexdigest()


def limit(request, category: str, identity: str, maximum: int, now: float, window: int = 900):
    """Atomic counters persist across processes/restarts; no raw emails/IPs stored."""
    key = digest(f"{category}:{identity}")
    with session_scope(request.app.state.engine) as session:
        session.execute(delete(AuthRateBucket).where(AuthRateBucket.expires_at <= now))
        statement = insert(AuthRateBucket).values(key=key, count=1, expires_at=now + window)
        statement = statement.on_conflict_do_update(
            index_elements=[AuthRateBucket.key], set_={"count": AuthRateBucket.count + 1}
        ).returning(AuthRateBucket.count, AuthRateBucket.expires_at)
        count, expires_at = session.execute(statement).one()
    if count > maximum:
        raise HTTPException(429, "Too many attempts. Please try again later.",
                            headers={"Retry-After": str(max(1, int(expires_at - now)))})


def limit_auth(request, email: str, now: float):
    limit(request, "auth-ip", request.client.host if request.client else "unknown", 60, now)
    limit(request, "auth-account", email, 10, now)


def revoke_session(request):
    token = request.session.get("token")
    if isinstance(token, str):
        with session_scope(request.app.state.engine) as session:
            session.execute(delete(LoginSession).where(LoginSession.token_hash == digest(token)))
    request.session.clear()


def start_session(request, session, user_id: int, now: float, idle_seconds: int):
    token = secrets.token_urlsafe(32)
    session.execute(delete(LoginSession).where(LoginSession.expires_at <= now))
    session.add(LoginSession(token_hash=digest(token), user_id=user_id,
                             expires_at=now + idle_seconds,
                             absolute_expires_at=now + ABSOLUTE_SESSION_SECONDS))
    request.session.clear()
    request.session.update(token=token, last_activity=now)


def send_verification_email(email: str, code: str):
    """TLS is mandatory. No development bypass or codes in application logs."""
    host, sender = os.getenv("SMTP_HOST"), os.getenv("SMTP_FROM")
    if not host or not sender:
        raise RuntimeError("Verification email delivery is not configured")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = email
    message["Subject"] = "Verify your Team Science email"
    message.set_content(f"Your Team Science verification code is: {code}\n\n"
                        "Enter it in the browser where you signed up or signed in. "
                        "It expires in 10 minutes. If you did not request this, ignore this email.")
    port = int(os.getenv("SMTP_PORT", "587"))
    context = ssl.create_default_context()
    implicit_tls = os.getenv("SMTP_SECURITY", "starttls") == "ssl"
    if os.getenv("SMTP_SECURITY", "starttls") not in {"ssl", "starttls"}:
        raise RuntimeError("SMTP_SECURITY must be ssl or starttls")
    connection = (smtplib.SMTP_SSL(host, port, timeout=15, context=context)
                  if implicit_tls else smtplib.SMTP(host, port, timeout=15))
    with connection as smtp:
        if not implicit_tls:
            smtp.starttls(context=context)
        username = os.getenv("SMTP_USERNAME")
        if username:
            smtp.login(username, os.environ["SMTP_PASSWORD"])
        smtp.send_message(message)
