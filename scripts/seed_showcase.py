"""Offline, idempotent seed: python -m scripts.seed_showcase."""
import os
from pathlib import Path

from backend.database.connection import create_sqlite_engine, initialize_database, DEFAULT_DATABASE_PATH
from backend.database.dataset_store import DatasetStore
from backend.services.analysis_service import AnalysisService
from backend.services.showcase import seed_showcase


def main():
    path = Path(os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH)))
    engine = create_sqlite_engine(path)
    initialize_database(engine)
    try:
        store = DatasetStore(os.getenv("DATASET_STORAGE_DIR", str(path.parent / "datasets")))
        print(f"Showcase report: /reports/{seed_showcase(AnalysisService(engine, store))}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
