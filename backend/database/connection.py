"""Explicit SQLite initialization and transaction boundaries.

Importing this module does not open a database or create files.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Union

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.models import Base

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "analysis.sqlite3"


def create_sqlite_engine(
    database_path: Union[str, Path] = DEFAULT_DATABASE_PATH,
) -> Engine:
    """Create an engine for a local file or an isolated ``:memory:`` database.

    Relative paths are resolved against the caller's working directory. The
    default path is anchored to the project. Dispose the engine when finished.
    """
    in_memory = str(database_path) == ":memory:"
    if in_memory:
        path = ":memory:"
    else:
        resolved_path = Path(database_path).expanduser().resolve()
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        path = str(resolved_path)

    options = {"poolclass": StaticPool} if in_memory else {}
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=path),
        connect_args={"check_same_thread": False},
        **options,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _connection_record):
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
        finally:
            cursor.close()

    return engine


def initialize_database(engine: Engine) -> None:
    """Create missing tables and indexes without deleting existing records.

    """
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Commit on success, roll back on error, and always close the session.

    Repositories only flush. Callers group related writes with this context.
    Loaded scalar attributes remain readable after the context exits.
    """
    with Session(engine, expire_on_commit=False) as session:
        with session.begin():
            yield session
