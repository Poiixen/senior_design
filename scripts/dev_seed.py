"""Create two known test accounts in the local database (development only).

Usage, from the repo root:
    python scripts/dev_seed.py

Then log in once and reuse the cookie:
    curl -c jar.txt -H "Content-Type: application/json" \
      -d '{"email":"dev1@example.com","password":"devpassword1"}' \
      http://127.0.0.1:8000/api/auth/login
    curl -b jar.txt -F file=@data.csv http://127.0.0.1:8000/api/analyze
    curl -b jar.txt http://127.0.0.1:8000/api/reports

Uses DATABASE_PATH like the server does. Safe to run repeatedly.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.database import repository  # noqa: E402
from backend.database.connection import (  # noqa: E402
    DEFAULT_DATABASE_PATH,
    create_sqlite_engine,
    initialize_database,
    session_scope,
)
from backend.services import auth_service  # noqa: E402

DEV_USERS = [
    ("dev1@example.com", "devpassword1"),
    ("dev2@example.com", "devpassword2"),
]


def main() -> None:
    engine = create_sqlite_engine(os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH)))
    initialize_database(engine)
    with session_scope(engine) as session:
        for email, password in DEV_USERS:
            if repository.get_user_by_email(session, email) is None:
                repository.create_user(
                    session,
                    email=email,
                    password_hash=auth_service.hash_password(password),
                )
                print(f"created {email} / {password}")
            else:
                print(f"exists  {email}")
    engine.dispose()


if __name__ == "__main__":
    main()
