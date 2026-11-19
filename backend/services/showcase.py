"""Prepared synthetic showcase; identity is tied to a reserved dataset marker."""
import secrets

import pandas as pd
from sqlalchemy import select

from backend.database import repository
from backend.database.connection import session_scope
from backend.models import Dataset
from backend.services.auth_service import hash_password

SOURCE = "team-science-showcase-v1"
EMAIL = "showcase@demo.invalid"


def is_demo_user(engine, user_id):
    with session_scope(engine) as session:
        return session.scalar(select(Dataset.id).where(
            Dataset.user_id == user_id, Dataset.source == SOURCE)) is not None


def showcase_report(service):
    with session_scope(service.engine) as session:
        user = repository.get_user_by_email(session, EMAIL)
        if user is None or not is_demo_user(service.engine, user.id):
            return None
        reports = repository.list_analysis_reports_for_user(session, user.id)
    return (user, reports[0]["analysis_id"]) if reports else None


def seed_showcase(service):
    """Run offline, one seeder at a time. Reuse dataset/report/comparisons after interruption."""
    frame = pd.DataFrame({
        "workshop": ["Morning" if i % 2 else "Evening" for i in range(80)],
        "minutes": [float(25 + i % 13 + (i % 2) * 8) for i in range(80)],
        "completed": ["Yes" if i % 5 else "No" for i in range(80)],
        "rating": [None if i % 10 == 0 else float(2 + i % 4) for i in range(80)],
    })
    frame.loc[79, "minutes"] = 180
    frame = pd.concat([frame, frame.iloc[:3]], ignore_index=True)
    with session_scope(service.engine) as session:
        user = repository.get_user_by_email(session, EMAIL)
        dataset = session.scalar(select(Dataset).where(Dataset.source == SOURCE))
        if user is None:
            user = repository.create_user(session, email=EMAIL,
                password_hash=hash_password(secrets.token_urlsafe(48)))
        elif dataset is None:
            raise ValueError("Reserved demo email already exists without a showcase dataset; choose a fresh database or resolve ownership offline.")
        if dataset is not None and dataset.user_id != user.id:
            raise ValueError("Showcase ownership mismatch")
        if dataset is None:
            # Commit the identity and its read-only marker together. A failed
            # Parquet write must not strand an unmarked reserved account.
            dataset = repository.create_dataset(session, name="Synthetic workshop attendance",
                source=SOURCE, file_name="showcase-workshops.csv", user_id=user.id,
                row_count=len(frame), column_count=len(frame.columns))
        service.dataset_store.save(dataset.id, frame)
    with session_scope(service.engine) as session:
        reports = repository.list_analysis_reports_for_user(session, user.id)
    analysis_id = reports[0]["analysis_id"] if reports else service.run_analysis(dataset.id, frame).id
    saved = service.list_comparisons(analysis_id, user.id)
    for kind, column in [("categorical_numeric", "minutes"), ("categorical_categorical", "completed")]:
        if not any(c["comparison_type"] == kind for c in saved):
            service.compare_columns(analysis_id, user.id, kind, "workshop", column)
    return analysis_id
