"""Tests for the /api/analyze endpoint."""

from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)


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
    assert "issues_detected" in body["summary"]
    assert isinstance(body["diagnostics"], list)


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
