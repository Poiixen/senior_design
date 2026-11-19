"""Run inside the API container to enable/rotate the shared demo login."""
import os

from backend.database import repository
from backend.database.connection import create_sqlite_engine, session_scope
from backend.services.auth_service import hash_password
from backend.services.showcase import EMAIL, is_demo_user

password = os.environ.get("DEMO_PASSWORD", "")
if not 8 <= len(password) <= 1024:
    raise SystemExit("Set DEMO_PASSWORD to between 8 and 1024 characters.")
engine = create_sqlite_engine(os.environ["DATABASE_PATH"])
try:
    with session_scope(engine) as session:
        user = repository.get_user_by_email(session, EMAIL)
        if user is None or not is_demo_user(engine, user.id):
            raise SystemExit("Protected demo account not found. Seed it first.")
        user.password_hash = hash_password(password)
    print(f"Shared demo login ready: {EMAIL}")
finally:
    engine.dispose()
