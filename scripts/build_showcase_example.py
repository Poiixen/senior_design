"""Regenerate browser fixtures from the real offline seed, using temporary storage."""
import json
import tempfile
from pathlib import Path

from backend.database.connection import create_sqlite_engine, initialize_database
from backend.database.dataset_store import DatasetStore
from backend.models.suggestions import SuggestionRequest
from backend.services.analysis_service import AnalysisService
from backend.services.showcase import seed_showcase, showcase_report
from backend.services.suggestions import generate_suggestions


def main():
    with tempfile.TemporaryDirectory() as directory:
        engine = create_sqlite_engine(Path(directory) / "analysis.sqlite3")
        initialize_database(engine)
        try:
            service = AnalysisService(engine, DatasetStore(Path(directory) / "datasets"))
            analysis_id = seed_showcase(service)
            user, _ = showcase_report(service)
            fixture = {"report": service.get_report(analysis_id), "suggestions": generate_suggestions(
                service, analysis_id, user.id, SuggestionRequest(limit=20))}
            output = Path(__file__).resolve().parents[1] / "docs/examples/showcase.json"
            output.write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding="utf-8")
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
