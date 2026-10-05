"""End-to-end checks that /api/analyze persists what it returns.

The API tests and the service tests each cover one side of this path: the
endpoint's response shape, and the repository's transactions. These tests
join the two, asserting that a single upload produces findings in the
response, the same findings in the database, and a retrievable report that
matches the response byte for byte.

The database is the throwaway SQLite file that conftest points DATABASE_PATH
at, so nothing here touches the repository's data/ directory.
"""

import json

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from backend.api.main import app, engine
from backend.database.connection import session_scope
from backend.database.repository import list_diagnostic_results
from backend.models import Analysis, AnalysisReport

client = TestClient(app)


# 20 rows with hand-checked diagnostics:
#   - "reading" is missing twice (10%, severity "moderate")
#   - the last two rows duplicate the first two (2 rows, 10%)
#   - "score" holds one extreme value, 500, against a 6.625..15.625 IQR band
MIXED_FINDINGS_CSV = (
    "sample_id,score,reading,group\n"
    "a1,10,1.0,x\n"
    "a2,11,2.0,y\n"
    "a3,12,3.0,x\n"
    "a4,13,4.0,y\n"
    "a5,10,5.0,x\n"
    "a6,11,,y\n"
    "a7,12,7.0,x\n"
    "a8,13,8.0,y\n"
    "a9,10,9.0,x\n"
    "a10,11,10.0,y\n"
    "a11,12,,x\n"
    "a12,13,12.0,y\n"
    "a13,10,13.0,x\n"
    "a14,11,14.0,y\n"
    "a15,500,15.0,x\n"
    "a16,12,16.0,y\n"
    "a17,13,17.0,x\n"
    "a18,10,18.0,y\n"
    "a1,10,1.0,x\n"
    "a2,11,2.0,y\n"
)


def upload(csv_content: str, filename: str = "fixture.csv", **form):
    return client.post(
        "/api/analyze",
        files={"file": (filename, csv_content, "text/csv")},
        data=form or None,
    )


def latest_analysis_id() -> int | None:
    """The highest analysis ID, including runs that failed."""
    with session_scope(engine) as session:
        return session.scalar(select(Analysis.id).order_by(Analysis.id.desc()).limit(1))


def stored_report(analysis_id: int) -> dict | None:
    with session_scope(engine) as session:
        record = session.get(AnalysisReport, analysis_id)
        return record.report if record is not None else None


def stored_report_text(analysis_id: int) -> str:
    """The report column exactly as written, before any JSON decoding."""
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT report FROM analysis_reports WHERE analysis_id = :id"),
            {"id": analysis_id},
        ).scalar_one()


def assert_strict_json(raw: str) -> None:
    """Reject the NaN/Infinity literals that Python tolerates but JSON forbids.

    json.loads accepts them by default, so a round trip through Python alone
    would not notice. Anything else reading the column -- SQLite's
    json_extract, a browser, jq -- would fail on them.
    """
    def reject(literal: str):
        raise AssertionError(f"stored report contains invalid JSON literal: {literal}")

    json.loads(raw, parse_constant=reject)


# --- Findings in the response -----------------------------------------


def test_upload_reports_missing_values_duplicates_and_outlier():
    """The three finding types land in the response with exact values."""
    response = upload(MIXED_FINDINGS_CSV)

    assert response.status_code == 200
    body = response.json()

    assert body["dataset"] == {"rows": 20, "columns": 4}
    assert body["status"] == "completed"

    assert body["missing_values"] == [
        {
            "column_name": "reading",
            "missing_count": 2,
            "missing_percentage": 10.0,
            "severity": "moderate",
        }
    ]

    score = next(e for e in body["outliers"] if e["column_name"] == "score")
    assert score["outlier_count"] == 1
    assert score["outlier_percentage"] == 5.0
    assert score["lower_bound"] == 6.625
    assert score["upper_bound"] == 15.625

    reading = next(e for e in body["outliers"] if e["column_name"] == "reading")
    assert reading["outlier_count"] == 0

    duplicates = next(e for e in body["diagnostics"] if e["type"] == "duplicates")
    assert duplicates["duplicate_count"] == 2
    assert duplicates["duplicate_percentage"] == 10.0

    assert body["summary"]["duplicate_rows"] == 2
    assert body["summary"]["missing_columns"] == 1
    assert body["summary"]["outlier_columns"] == 1
    assert body["summary"]["numeric_columns"] == 2
    assert body["summary"]["categorical_columns"] == 2
    assert body["validation"]["valid"] is True
    assert body["validation"]["warnings"] == []


# --- Response matches what was saved ----------------------------------


def test_saved_report_matches_the_response_it_came_from():
    """Re-reading the report returns exactly the uploaded response."""
    body = upload(MIXED_FINDINGS_CSV).json()
    analysis_id = body["analysis_id"]

    retrieved = client.get(f"/api/reports/{analysis_id}")
    assert retrieved.status_code == 200
    assert retrieved.json() == body

    # Served from the database, not from a cache in the request path.
    assert stored_report(analysis_id) == body


def test_saved_findings_match_the_reported_findings():
    """The diagnostic rows written by the service agree with the response."""
    body = upload(MIXED_FINDINGS_CSV).json()
    analysis_id = body["analysis_id"]

    with session_scope(engine) as session:
        saved = list_diagnostic_results(session, analysis_id)

    missing = [r for r in saved if r.diagnostic_type == "missing_values"]
    assert [(r.column_name, r.value, r.severity) for r in missing] == [
        ("reading", 10.0, "moderate")
    ]

    duplicates = [r for r in saved if r.diagnostic_type == "duplicates"]
    assert len(duplicates) == 1
    assert duplicates[0].column_name is None
    assert duplicates[0].value == 10.0
    assert duplicates[0].severity == "warning"


def test_each_upload_is_persisted_as_a_separate_report():
    """Two uploads keep independent IDs, findings and report snapshots."""
    first = upload(MIXED_FINDINGS_CSV, filename="first.csv").json()
    second = upload(MIXED_FINDINGS_CSV, filename="second.csv").json()

    assert first["analysis_id"] != second["analysis_id"]
    assert first["filename"] == "first.csv"
    assert second["filename"] == "second.csv"

    assert client.get(f"/api/reports/{first['analysis_id']}").json() == first
    assert client.get(f"/api/reports/{second['analysis_id']}").json() == second


# --- Failure leaves nothing behind ------------------------------------


def test_detector_failure_leaves_no_findings_and_no_report(monkeypatch):
    """A failed run is recorded as failed, with no findings and no report."""
    def explode(df):
        raise RuntimeError("detector failed")

    monkeypatch.setattr(
        "backend.services.analysis_service.detect_duplicates", explode
    )

    before = latest_analysis_id()
    response = upload(MIXED_FINDINGS_CSV, filename="broken.csv")

    assert response.status_code == 500
    # The generic handler must not leak the underlying exception.
    assert "detector failed" not in response.text

    analysis_id = latest_analysis_id()
    assert analysis_id is not None and analysis_id != before

    with session_scope(engine) as session:
        analysis = session.get(Analysis, analysis_id)
        assert analysis.status == "failed"
        assert analysis.completed_at is not None
        assert list_diagnostic_results(session, analysis_id) == []

    assert stored_report(analysis_id) is None
    assert client.get(f"/api/reports/{analysis_id}").status_code == 404


def test_partial_write_failure_rolls_back_every_finding(monkeypatch):
    """Failing midway through the inserts leaves no partial findings."""
    import backend.services.analysis_service as service

    real_save = service.repository.save_diagnostic_result
    calls = {"n": 0}

    def fail_on_second(session, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("insert failed")
        return real_save(session, **kwargs)

    monkeypatch.setattr(
        service.repository, "save_diagnostic_result", fail_on_second
    )

    before = latest_analysis_id()
    response = upload(MIXED_FINDINGS_CSV, filename="partial.csv")

    assert response.status_code == 500
    assert calls["n"] >= 2, "the second insert should have been reached"

    analysis_id = latest_analysis_id()
    assert analysis_id is not None and analysis_id != before

    with session_scope(engine) as session:
        analysis = session.get(Analysis, analysis_id)
        assert analysis.status == "failed"
        # The first insert succeeded before the second raised; the
        # transaction must have discarded it.
        assert list_diagnostic_results(session, analysis_id) == []

    assert stored_report(analysis_id) is None
    assert client.get(f"/api/reports/{analysis_id}").status_code == 404


def test_rejected_upload_creates_no_analysis_at_all():
    """Input rejected before analysis starts leaves the database untouched."""
    before = latest_analysis_id()

    assert upload("", filename="empty.csv").status_code == 400
    assert upload("a,b\n1,2\n", filename="notes.txt").status_code == 400

    assert latest_analysis_id() == before


# --- Edge-case inputs --------------------------------------------------


def test_warning_only_input_is_analyzed_and_persisted():
    """Warnings do not block analysis, and they survive the round trip."""
    body = upload("a,b\n1,p\n2,q\n3,r\n", filename="small.csv").json()

    assert body["status"] == "completed"
    assert body["validation"]["valid"] is True
    assert body["validation"]["errors"] == []
    assert body["validation"]["warnings"] == [
        "Dataset is extremely small (fewer than 5 rows)"
    ]

    warnings = [
        e
        for e in body["diagnostics"]
        if e["type"] == "validation" and e["severity"] == "warning"
    ]
    assert len(warnings) == 1
    assert body["missing_values"] == []
    assert body["summary"]["duplicate_rows"] == 0

    assert client.get(f"/api/reports/{body['analysis_id']}").json() == body


def test_all_missing_numeric_column_serializes_and_persists():
    """An all-NaN numeric column yields JSON nulls, not NaN, and round trips."""
    body = upload(
        "label,measure\nr1,\nr2,\nr3,\nr4,\nr5,\n", filename="empty-column.csv"
    ).json()

    assert body["status"] == "completed"
    assert body["missing_values"] == [
        {
            "column_name": "measure",
            "missing_count": 5,
            "missing_percentage": 100.0,
            "severity": "high",
        }
    ]

    measure = next(e for e in body["outliers"] if e["column_name"] == "measure")
    assert measure["outlier_count"] == 0
    # Quartiles are undefined with no values, so each bound has to be null.
    for field in ("q1", "q3", "iqr", "lower_bound", "upper_bound"):
        assert measure[field] is None, f"{field} should serialize as null"

    assert body["validation"]["warnings"] == [
        "Completely empty columns found: ['measure']"
    ]

    # The response alone cannot prove the NaN was handled: FastAPI's encoder
    # renders a float NaN as null on its way out regardless. The stored column
    # is where an unguarded NaN actually survives, as a bare literal that is
    # not valid JSON, so assert on the raw text that was written.
    assert_strict_json(stored_report_text(body["analysis_id"]))

    retrieved = client.get(f"/api/reports/{body['analysis_id']}")
    assert retrieved.json() == body


# --- Listing -----------------------------------------------------------


def test_report_listing_summarizes_without_the_full_payload():
    """The index carries summary fields only, newest first."""
    body = upload(MIXED_FINDINGS_CSV, filename="listed.csv").json()

    listing = client.get("/api/reports")
    assert listing.status_code == 200
    reports = listing.json()["reports"]

    newest = reports[0]
    assert newest["analysis_id"] == body["analysis_id"]
    assert newest["filename"] == "listed.csv"
    assert newest["summary"] == body["summary"]
    for omitted in ("missing_values", "outliers", "diagnostics", "validation"):
        assert omitted not in newest

    ids = [r["analysis_id"] for r in reports]
    assert ids == sorted(ids, reverse=True)
