"""Tests for the /api/analyze endpoint."""

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app, get_analysis_service
from backend.database import repository
from backend.database.connection import (
    create_sqlite_engine,
    initialize_database,
    session_scope,
)
from backend.services import AnalysisService
from backend.services import analysis_service as service_module

MIXED_CSV = (
    "name,age\n"
    "Alice,20\n"
    "Bob,\n"
    "Alice,20\n"
)


@pytest.fixture
def engine(tmp_path):
    engine = create_sqlite_engine(tmp_path / "api.sqlite3")
    initialize_database(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(engine):
    app.dependency_overrides[get_analysis_service] = lambda: AnalysisService(engine)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _post(client, content, name="data.csv"):
    return client.post("/api/analyze", files={"file": (name, content, "text/csv")})


def test_analyze_returns_expected_shape(client):
    response = _post(client, MIXED_CSV)

    assert response.status_code == 200
    body = response.json()

    assert isinstance(body["analysis_id"], int)
    assert isinstance(body["dataset_id"], int)
    assert body["report"]["analysis_id"] == body["analysis_id"]
    assert body["report"]["dataset_id"] == body["dataset_id"]
    assert body["report"]["summary"]["issues_detected"] == body["summary"]["issues_detected"]
    assert body["dataset"] == {"rows": 3, "columns": 2}
    assert "issues_detected" in body["summary"]
    assert isinstance(body["diagnostics"], list)
    assert {entry["column"] for entry in body["profile"]} == {"name", "age"}
    for entry in body["diagnostics"]:
        assert set(entry) == {"type", "column", "severity", "value", "message"}


def test_analyze_reports_missing_values_and_duplicates(client):
    body = _post(client, MIXED_CSV).json()
    diagnostic_types = {entry["type"] for entry in body["diagnostics"]}

    assert "missing_values" in diagnostic_types
    assert "duplicates" in diagnostic_types
    assert "validation" in diagnostic_types
    assert body["summary"]["issues_detected"] == len(body["diagnostics"])


def test_analyze_reports_outliers_and_omits_clean_findings(client):
    csv_content = "value\n" + "\n".join(str(v) for v in [-100, *range(1, 10), 100])
    body = _post(client, csv_content).json()

    outliers = [entry for entry in body["diagnostics"] if entry["type"] == "outliers"]
    assert len(outliers) == 1
    assert outliers[0]["column"] == "value"
    assert all(entry["type"] != "duplicates" for entry in body["diagnostics"])
    assert all(entry["severity"] not in {"none", "info"} for entry in body["diagnostics"])


def test_analyze_persists_dataset_and_findings(client, engine):
    body = _post(client, MIXED_CSV, name="people.csv").json()

    with session_scope(engine) as session:
        (dataset,) = repository.list_datasets(session)
        (analysis,) = repository.list_analyses(session, dataset.id)
        results = repository.list_diagnostic_results(session, analysis.id)

    assert dataset.file_name == "people.csv"
    assert (dataset.row_count, dataset.column_count) == (3, 2)
    assert analysis.id == body["analysis_id"]
    assert analysis.status == "completed"
    assert len(results) == len(body["diagnostics"]) + len(body["profile"]) + sum(
        1 for result in results if result.severity == "none"
    )


def test_lifespan_initializes_and_disposes_engine(tmp_path, monkeypatch):
    from backend.api import main as main_module

    engines = []
    disposed = []

    def make_engine():
        engine = create_sqlite_engine(tmp_path / "lifespan.sqlite3")
        original_dispose = engine.dispose
        engine.dispose = lambda *a, **k: (disposed.append(True), original_dispose(*a, **k))
        engines.append(engine)
        return engine

    monkeypatch.setattr(main_module, "create_sqlite_engine", make_engine)

    with TestClient(app) as lifespan_client:
        assert len(engines) == 1
        assert disposed == []
        response = _post(lifespan_client, MIXED_CSV)
        assert response.status_code == 200

    assert disposed == [True]
    with session_scope(create_sqlite_engine(tmp_path / "lifespan.sqlite3")) as session:
        assert len(repository.list_datasets(session)) == 1


def test_analyze_rejects_empty_csv(client):
    response = _post(client, "", name="empty.csv")

    assert response.status_code == 400


def test_analyze_rejects_structurally_invalid_dataset(client, monkeypatch):
    # load_csv already rejects files the validator would block, so force it.
    monkeypatch.setattr(
        service_module,
        "validate_dataset",
        lambda df: {"valid": False, "errors": ["Broken structure"], "warnings": []},
    )

    response = _post(client, MIXED_CSV)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail["analysis_id"], int)
    assert detail["errors"] == ["Broken structure"]


def test_saved_report_can_be_retrieved(client):
    body = _post(client, MIXED_CSV).json()

    response = client.get(f"/api/analyses/{body['analysis_id']}/report")

    assert response.status_code == 200
    assert response.json() == body["report"]


def test_missing_report_returns_404(client):
    assert client.get("/api/analyses/999/report").status_code == 404
