"""Public showcase uses real persisted analyses without shared write access."""
import pytest

from backend.api.main import app
from backend.database.connection import session_scope
from backend.database import repository
from backend.services.showcase import seed_showcase, EMAIL


def test_seed_idempotent_and_repair_missing_parquet(client):
    service = app.state.analysis_service
    first = seed_showcase(service)
    assert seed_showcase(service) == first
    with session_scope(service.engine) as session:
        user = repository.get_user_by_email(session, EMAIL)
        assert len(repository.list_analysis_reports_for_user(session, user.id)) == 1
        analysis = repository.get_analysis_for_user(session, first, user.id)
    service.dataset_store.path(analysis.dataset_id).unlink()
    assert seed_showcase(service) == first
    assert service.dataset_store.load(analysis.dataset_id) is not None
    assert len(service.list_comparisons(first, user.id)) == 2


def test_demo_login_cannot_bypass_verification(client, monkeypatch):
    monkeypatch.setenv("SHOWCASE_ENABLED", "true")
    analysis_id = seed_showcase(app.state.analysis_service)
    assert client.post("/api/auth/demo").status_code == 403
    assert client.get(f"/api/reports/{analysis_id}").status_code == 401
    from conftest import register_user
    register_user(client, email="visitor@example.org")
    assert client.get(f"/api/reports/{analysis_id}").status_code == 404

def test_demo_disabled_and_reserved_identity(client, monkeypatch):
    monkeypatch.delenv("SHOWCASE_ENABLED", raising=False)
    assert client.post("/api/auth/demo").status_code == 403
    assert client.post("/api/auth/register", json={"email": EMAIL, "password": "some-password"}).status_code == 400


def test_failed_seed_rolls_back_identity_and_can_retry(client, monkeypatch):
    service = app.state.analysis_service
    original = service.dataset_store.save
    def fail(*args):
        raise OSError("Simulated full disk")
    monkeypatch.setattr(service.dataset_store, "save", fail)
    with pytest.raises(OSError):
        seed_showcase(service)
    with session_scope(service.engine) as session:
        assert repository.get_user_by_email(session, EMAIL) is None
    monkeypatch.setattr(service.dataset_store, "save", original)
    assert seed_showcase(service) > 0


def test_seed_survives_new_engine(tmp_path):
    from backend.database.connection import create_sqlite_engine, initialize_database
    from backend.database.dataset_store import DatasetStore
    from backend.services.analysis_service import AnalysisService
    database = tmp_path / "persist.sqlite3"
    store = DatasetStore(tmp_path / "datasets")
    engine = create_sqlite_engine(database)
    initialize_database(engine)
    first = seed_showcase(AnalysisService(engine, store))
    engine.dispose()
    restarted = create_sqlite_engine(database)
    try:
        service = AnalysisService(restarted, store)
        assert seed_showcase(service) == first
        assert service.get_report(first)["dataset"]["rows"] == 83
    finally:
        restarted.dispose()
