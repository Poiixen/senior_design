"""Tests for the /api/analyze endpoint."""

import pytest
from fastapi.testclient import TestClient

from backend.api import main as main_module
from backend.api.main import app
from backend.database import repository
from backend.database.connection import session_scope
from backend.services import analysis_service as service_module

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def app_lifespan():
    """Run application startup and shutdown around this module's requests."""
    with client:
        yield


def test_analyze_returns_expected_shape():
    csv_content = (
        "name,age\n"
        "Alice,20\n"
        "Bob,\n"
        "Alice,20\n"
    )

    response = client.post(
        "/api/analyze",
        files={"file": ("data.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()

    assert body["dataset"] == {"rows": 3, "columns": 2}
    assert body["analysis_id"] > 0
    assert body["filename"] == "data.csv"
    assert body["status"] == "completed"
    assert body["completed_at"] is not None
    assert body["summary"]["numeric_columns"] == 1
    assert body["summary"]["categorical_columns"] == 1
    assert body["parsing_options"] == {
        "delimiter": ",",
        "has_header": True,
        "missing_values": [],
    }
    assert isinstance(body["missing_values"], list)
    assert isinstance(body["outliers"], list)
    assert body["validation"]["valid"] is True
    assert isinstance(body["diagnostics"], list)

    saved_response = client.get(f"/api/reports/{body['analysis_id']}")
    assert saved_response.status_code == 200
    assert saved_response.json() == body

    list_response = client.get("/api/reports")
    assert list_response.status_code == 200
    listed = list_response.json()["reports"]
    assert listed[0]["analysis_id"] == body["analysis_id"]
    assert listed[0]["filename"] == "data.csv"
    assert "missing_values" not in listed[0]


def test_analyze_reports_missing_values_and_duplicates():
    csv_content = (
        "name,age\n"
        "Alice,20\n"
        "Bob,\n"
        "Alice,20\n"
    )

    response = client.post(
        "/api/analyze",
        files={"file": ("data.csv", csv_content, "text/csv")},
    )

    body = response.json()
    diagnostic_types = {entry["type"] for entry in body["diagnostics"]}

    assert "missing_values" in diagnostic_types
    assert "duplicates" in diagnostic_types
    assert body["summary"]["issues_detected"] == len(body["diagnostics"])


def test_analyze_rejects_empty_csv():
    response = client.post(
        "/api/analyze",
        files={"file": ("empty.csv", "", "text/csv")},
    )

    assert response.status_code == 400


def test_analyze_honors_header_delimiter_and_missing_markers():
    response = client.post(
        "/api/analyze",
        files={"file": ("data.csv", "Alice;10\n ?;20\n", "text/csv")},
        data={
            "delimiter": ";",
            "has_header": "false",
            "missing_values": "[]",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["dataset"] == {"rows": 2, "columns": 2}
    assert body["parsing_options"] == {
        "delimiter": ";",
        "has_header": False,
        "missing_values": [],
    }
    assert body["missing_values"] == [
        {
            "column_name": "0",
            "missing_count": 1,
            "missing_percentage": 50.0,
            "severity": "high",
        }
    ]


def test_report_lookup_returns_not_found():
    response = client.get("/api/reports/999999999")

    assert response.status_code == 404


MIXED_CSV = "name,age\nAlice,20\nBob,\nAlice,20\n"


def _post(content=MIXED_CSV):
    return client.post("/api/analyze", files={"file": ("data.csv", content, "text/csv")})


def test_report_adds_versioned_ids_and_findings_to_the_frontend_shape():
    body = _post().json()

    assert body["schema_version"] == 1
    assert isinstance(body["dataset_id"], int)
    findings = {(f["diagnostic"], f["column"]): f for f in body["findings"]}
    missing = findings[("missing_values", "age")]
    assert missing["metadata"] == {"missing_count": 1, "total_rows": 3}
    assert missing["recommendation"]
    assert findings[("duplicates", None)]["metadata"]["duplicate_count"] == 1


def test_analysis_runs_each_diagnostic_once_per_upload(monkeypatch):
    calls = []
    original = service_module.profile_dataset

    def counted(frame):
        calls.append(1)
        return original(frame)

    monkeypatch.setattr(service_module, "profile_dataset", counted)

    assert _post().status_code == 200
    assert len(calls) == 1


def test_failed_run_has_no_report_and_returns_conflict(monkeypatch):
    def fail(frame):
        raise RuntimeError("Detector failed")

    monkeypatch.setattr(service_module, "profile_dataset", fail)
    assert _post().status_code == 500

    with session_scope(main_module.engine) as session:
        dataset = repository.list_datasets(session)[-1]
        (analysis,) = repository.list_analyses(session, dataset.id)
        assert analysis.status == "failed"
        assert repository.list_diagnostic_results(session, analysis.id) == []

    response = client.get(f"/api/reports/{analysis.id}")
    assert response.status_code == 409
    assert "failed" in response.json()["detail"]


def test_lifespan_disposes_the_engine_on_shutdown(monkeypatch):
    disposed = []
    original = main_module.engine.dispose
    monkeypatch.setattr(
        main_module.engine,
        "dispose",
        lambda *a, **k: (disposed.append(True), original(*a, **k)),
    )

    with TestClient(app) as lifespan_client:
        assert disposed == []
        assert lifespan_client.get("/health").status_code == 200

    assert disposed == [True]
