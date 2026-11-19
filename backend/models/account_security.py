"""Persistent verification, revocable sessions, and shared authentication limits."""
from sqlalchemy import ForeignKey, Integer, Float, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.models.records import Base


class AccountVerification(Base):
    __tablename__ = "account_verifications"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    verified_at: Mapped[float | None] = mapped_column(Float)


class VerificationChallenge(Base):
    __tablename__ = "verification_challenges"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    code_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[float] = mapped_column(Float, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[float] = mapped_column(Float, index=True)
    absolute_expires_at: Mapped[float] = mapped_column(Float)


class AuthRateBucket(Base):
    __tablename__ = "auth_rate_buckets"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[float] = mapped_column(Float, index=True)
