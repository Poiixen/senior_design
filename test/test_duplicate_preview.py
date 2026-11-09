"""The preview counts exact extra rows without mutating source or saved evidence."""
from fastapi.testclient import TestClient

from backend.api.main import app
from conftest import register_user


def upload(client, csv="group,score\nA,1\nA,1\nB,3\nB,4\nB,4\n"):
    response = client.post("/api/analyze", files={"file": ("preview.csv", csv, "text/csv")})
    assert response.status_code == 200
    return response.json()


def test_preview_preserves_source_report_and_comparisons(auth_client):
    report = upload(auth_client)
    aid = report["analysis_id"]
    base = f"/api/reports/{aid}"
    comparison = auth_client.post(f"{base}/comparisons", json={
        "comparison_type": "categorical_numeric", "group_column": "group", "value_column": "score",
    }).json()
    store = app.state.analysis_service.dataset_store
    paths = list(store.directory.glob("*.parquet"))
    before = {p: p.read_bytes() for p in paths}
    for _ in range(2):
        response = auth_client.post(f"{base}/duplicate-preview")
        assert response.status_code == 200
        preview = response.json()
        assert (preview["original_rows"], preview["proposed_removed_rows"], preview["resulting_rows"]) == (5, 2, 3)
        assert "No changes were applied" in preview["note"]
    assert {p: p.read_bytes() for p in paths} == before
    assert auth_client.get(base).json() == report
    assert auth_client.get(f"{base}/comparisons").json() == {"comparisons": [comparison]}


def test_preview_zero_duplicates_and_matching_missing_values(auth_client):
    for csv, removed in [("a,b\n1,x\n2,y\n", 0), ("a,b\n1,\n1,\n2,x\n", 1)]:
        report = upload(auth_client, csv)
        preview = auth_client.post(f"/api/reports/{report['analysis_id']}/duplicate-preview").json()
        assert preview["proposed_removed_rows"] == removed


def test_preview_requires_ownership_and_available_source(auth_client):
    report = upload(auth_client)
    url = f"/api/reports/{report['analysis_id']}/duplicate-preview"
    other = TestClient(app)
    assert other.post(url).status_code == 401
    register_user(other, "other@example.com")
    assert other.post(url).status_code == 404
    assert other.post("/api/reports/999999/duplicate-preview").status_code == 404
    app.state.analysis_service.dataset_store = None
    assert auth_client.post(url).status_code == 409


def test_profile_box_endpoints_are_observed_values(auth_client):
    report = upload(auth_client, "group,score\nA,1\nA,2\nA,3\nB,4\nB,100\n")
    profile = next(p for p in report["column_profiles"] if p["name"] == "score")
    assert [profile[k] for k in ("count", "q1", "median", "q3", "whisker_low", "whisker_high", "outlier_count")] == [5, 2, 3, 4, 1, 4, 1]
