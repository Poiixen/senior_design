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
