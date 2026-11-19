"""Set shared passwords interactively; never put passwords in shell history."""
import os
from getpass import getpass
from pathlib import Path

from sqlalchemy import delete

from backend.database import repository
from backend.database.connection import create_sqlite_engine, initialize_database, session_scope, DEFAULT_DATABASE_PATH
from backend.database.dataset_store import DatasetStore
from backend.models.account_security import LoginSession
from backend.services.analysis_service import AnalysisService
from backend.services.auth_service import hash_password
from backend.services.showcase import EMAIL, seed_showcase

ADMIN_EMAIL = "admin@teamscience.invalid"


def configure_accounts(service, admin_password, demo_password):
    if min(len(admin_password), len(demo_password)) < 15:
        raise ValueError("Use at least 15 characters for each password.")
    if admin_password == demo_password:
        raise ValueError("Admin and demo passwords must be different.")
    seed_showcase(service)
    with session_scope(service.engine) as session:
        for email, password in [(ADMIN_EMAIL, admin_password), (EMAIL, demo_password)]:
            user = repository.get_user_by_email(session, email)
            if user is None:
                user = repository.create_user(session, email=email, password_hash=hash_password(password))
            else:
                user.password_hash = hash_password(password)
            session.execute(delete(LoginSession).where(LoginSession.user_id == user.id))


def main():
    passwords = []
    for role in ["Admin", "Demo"]:
        password = getpass(f"{role} password (15+ characters): ")
        if password != getpass(f"Confirm {role.lower()} password: "):
            raise SystemExit("Passwords did not match. No changes made.")
        passwords.append(password)
    path = Path(os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH)))
    engine = create_sqlite_engine(path)
    try:
        initialize_database(engine)
        store = DatasetStore(os.getenv("DATASET_STORAGE_DIR", str(path.parent / "datasets")))
        configure_accounts(AnalysisService(engine, store), *passwords)
        print("Admin and demo access configured. Existing shared sessions revoked.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
