"""Password hashing and credential checks."""

from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy.orm import Session

from backend.database import repository
from backend.models import User

_hasher = PasswordHasher()
# Checked when an email is unknown so both failures take similar time.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def authenticate_user(session: Session, email: str, password: str) -> Optional[User]:
    """Return the user for valid credentials, otherwise None."""
    user = repository.get_user_by_email(session, normalize_email(email))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user.password_hash) else None
