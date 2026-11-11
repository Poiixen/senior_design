"""Duplicate-removal cleaning preview: counts, immutability and ownership."""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.diagnostics.duplicate_cleaning_preview import preview_duplicate_removal
from backend.diagnostics.duplicate_detection import detect_duplicates
from conftest import register_user

ACTION = {"action": "remove_exact_duplicates"}

# Rows 2 and 3 repeat row 1; row 6 repeats row 5 (both with an empty cell).
CSV = (
    "name,city,age\n"
    "Alice,Paris,30\n"
    "Alice,Paris,30\n"
    "Alice,Paris,30\n"
    "Bob,Rome,41\n"
    "Cara,,22\n"
    "Cara,,22\n"
    "Dan,Oslo,50\n"
)
NO_DUPLICATES_CSV = "name,age\nAlice,30\nBob,41\n"


def upload(client, csv=CSV):
    response = client.post("/api/analyze", files={"file": ("p.csv", csv, "text/csv")})
    assert response.status_code == 200
    return response.json()["analysis_id"]


def preview(client, analysis_id, body=ACTION):
    return client.post(f"/api/reports/{analysis_id}/cleaning-previews", json=body)


def test_preview_counts_and_row_references(auth_client):
    analysis_id = upload(auth_client)

    response = preview(auth_client, analysis_id)

    assert response.status_code == 200
    body = response.json()
    assert body["preview"] is True and body["applied"] is False
    assert body["status"] == "ok"
    assert body["counts"] == {"original_rows": 7, "removed_rows": 3, "resulting_rows": 4}
    assert body["duplicate_group_count"] == 2
    assert body["groups"] == [
        {"kept_row": 1, "removed_rows": [2, 3], "removed_count": 2},
        {"kept_row": 5, "removed_rows": [6], "removed_count": 1},
    ]
    assert "preview" in body["notes"][0].lower()
    assert len(body["dataset_version"]["content_hash"]) == 64


def test_preview_matches_existing_duplicate_diagnostic(auth_client):
    analysis_id = upload(auth_client)
    report = auth_client.get(f"/api/reports/{analysis_id}").json()

    body = preview(auth_client, analysis_id).json()

    assert body["counts"]["removed_rows"] == report["summary"]["duplicate_rows"]
    assert body["dataset_version"]["dataset_id"] == report["dataset_id"]


def test_preview_leaves_dataset_and_report_unchanged(auth_client):
    analysis_id = upload(auth_client)
    store = app.state.analysis_service.dataset_store
    report_before = auth_client.get(f"/api/reports/{analysis_id}").json()
    dataset_id = report_before["dataset_id"]
    rows_before = store.load(dataset_id)
    file_before = store.path(dataset_id).read_bytes()

    first = preview(auth_client, analysis_id).json()
    second = preview(auth_client, analysis_id).json()

    pd.testing.assert_frame_equal(store.load(dataset_id), rows_before)
    assert len(store.load(dataset_id)) == 7
    assert store.path(dataset_id).read_bytes() == file_before
    assert auth_client.get(f"/api/reports/{analysis_id}").json() == report_before
    assert first == second  # deterministic, same dataset version


def test_no_duplicates_dataset(auth_client):
    analysis_id = upload(auth_client, NO_DUPLICATES_CSV)

    response = preview(auth_client, analysis_id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_duplicates"
    assert body["counts"] == {"original_rows": 2, "removed_rows": 0, "resulting_rows": 2}
    assert body["groups"] == []


def test_unsupported_action_is_rejected(auth_client):
    analysis_id = upload(auth_client)

    response = preview(auth_client, analysis_id, {"action": "drop_missing_rows"})

    assert response.status_code == 400
    assert "remove_exact_duplicates" in response.json()["detail"]
    assert preview(auth_client, analysis_id, {}).status_code == 422


def test_unavailable_rows_give_409(auth_client):
    analysis_id = upload(auth_client)
    report = auth_client.get(f"/api/reports/{analysis_id}").json()
    app.state.analysis_service.dataset_store.path(report["dataset_id"]).unlink()

    response = preview(auth_client, analysis_id)

    assert response.status_code == 409
    assert "Upload the file again" in response.json()["detail"]


def test_changed_rows_give_409(auth_client):
    analysis_id = upload(auth_client)
    report = auth_client.get(f"/api/reports/{analysis_id}").json()
    store = app.state.analysis_service.dataset_store
    store.save(report["dataset_id"], store.load(report["dataset_id"]).iloc[:3])

    assert preview(auth_client, analysis_id).status_code == 409


def test_other_user_and_anonymous_cannot_preview(client):
    register_user(client, email="a@example.com")
    analysis_id = upload(client)
    other = TestClient(app)
    register_user(other, email="b@example.com")

    assert preview(other, analysis_id).status_code == 404
    assert preview(client, 999).status_code == 404
    assert preview(TestClient(app), analysis_id).status_code == 401


# --- Unit behavior ------------------------------------------------------


def test_preview_agrees_with_detect_duplicates_for_missing_values():
    df = pd.DataFrame({"a": ["x", "x", None, None, "y"], "b": [1, 1, np.nan, np.nan, np.nan]})

    result = preview_duplicate_removal(df)

    assert result["removed_row_count"] == detect_duplicates(df)["duplicate_count"] == 2
    assert result["resulting_row_count"] == 3


def test_groups_are_bounded_and_input_is_not_modified():
    df = pd.DataFrame({"a": [i // 2 for i in range(60)]})  # 30 groups of 2
    before = df.copy()

    result = preview_duplicate_removal(df)

    assert result["removed_row_count"] == 30
    assert result["duplicate_group_count"] == 30
    assert len(result["groups"]) == 10 and result["groups_truncated"] is True
    pd.testing.assert_frame_equal(df, before)
