"""SQLAlchemy models for metadata and summaries, never raw dataset rows.

Uploaded rows that later analyses need are kept on disk by
``backend.database.dataset_store``, not in these tables.

Timestamps are naive UTC datetimes, matching SQLite's DateTime storage.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint("row_count >= 0", name="ck_datasets_row_count"),
        CheckConstraint("column_count >= 0", name="ck_datasets_column_count"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Null only for datasets saved before accounts existed; nobody owns those.
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(Text)
    file_name: Mapped[Optional[str]] = mapped_column(Text)
    row_count: Mapped[int] = mapped_column(Integer)
    column_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_analyses_status",
        ),
        CheckConstraint(
            "(status = 'running' AND completed_at IS NULL) OR "
            "(status IN ('completed', 'failed') AND completed_at IS NOT NULL)",
            name="ck_analyses_completion",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    status: Mapped[str] = mapped_column(Text, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class DiagnosticResult(Base):
    __tablename__ = "diagnostic_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    diagnostic_type: Mapped[str] = mapped_column(Text)
    column_name: Mapped[Optional[str]] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    value: Mapped[Optional[float]] = mapped_column(Float)
    message: Mapped[str] = mapped_column(Text)


class AnalysisReport(Base):
    """A complete, JSON-safe report snapshot; no individual dataset rows.

    A separate table allows existing metadata databases to gain report storage
    through create_all without altering their existing columns.
    """

    __tablename__ = "analysis_reports"

    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id"), primary_key=True
    )
    report: Mapped[dict] = mapped_column(JSON)


class Comparison(Base):
    """A saved column comparison for one analysis's dataset.

    ``result`` is the JSON-safe comparison, including the selected columns,
    summaries, test results and warnings.
    """

    __tablename__ = "comparisons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    comparison_type: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    result: Mapped[dict] = mapped_column(JSON)


class Conversation(Base):
    """A follow-up question thread owned by one user about one report."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConversationMessage(Base):
    """One question or answer. ``request_id`` pairs a question with its answer.

    A retried request reuses its ``request_id``, so the unique constraint keeps
    a turn from being saved twice. ``sources`` lists the saved results an
    answer drew on; it is set by the backend, never copied from the model.
    """

    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_conversation_messages_role"),
        UniqueConstraint(
            "conversation_id", "role", "request_id", name="uq_conversation_messages_request"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    # Assistant messages only: "answered" or "insufficient_evidence".
    status: Mapped[Optional[str]] = mapped_column(Text)
    sources: Mapped[Optional[list]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
