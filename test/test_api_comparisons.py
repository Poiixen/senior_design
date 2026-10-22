"""Column comparisons through the API: saving, retrieval and ownership."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.database.dataset_store import DatasetStore
from conftest import register_user

CSV = (
    "education,income,age,country\n"
    "HS,<=50K,22,US\n"
    "HS,<=50K,25,US\n"
    "HS,>50K,41,US\n"
    "BA,>50K,38,US\n"
    "BA,<=50K,30,US\n"
    "BA,>50K,45,US\n"
    "MA,>50K,50,US\n"
    "MA,>50K,?,US\n"
    "?,<=50K,33,US\n"
)

CATEGORICAL = {
    "comparison_type": "categorical_categorical",
    "group_column": "education",
    "outcome_column": "income",
}
TWO_GROUPS = {
    "comparison_type": "categorical_numeric",
    "group_column": "income",
    "value_column": "age",
}
THREE_GROUPS = {**TWO_GROUPS, "group_column": "education"}


def upload(client):
    response = client.post(
        "/api/analyze", files={"file": ("people.csv", CSV, "text/csv")}
    )
    assert response.status_code == 200
    return response.json()["analysis_id"]


def compare(client, analysis_id, body):
    return client.post(f"/api/reports/{analysis_id}/comparisons", json=body)


def test_categorical_comparison_is_created(auth_client):
    analysis_id = upload(auth_client)

    response = compare(auth_client, analysis_id, CATEGORICAL)

    assert response.status_code == 201
    body = response.json()
    assert body["analysis_id"] == analysis_id
    assert body["comparison_type"] == "categorical_categorical"
    assert body["selection"] == {"group_column": "education", "outcome_column": "income"}
    assert body["rows"]["excluded"] == 1  # the '?' education row
    assert body["group_categories"] == ["BA", "HS", "MA"]
    assert body["counts"] == [[2, 1], [1, 2], [2, 0]]
    assert body["test"]["status"] == "ok"
    assert body["warnings"]  # 8 rows: expected counts are small


def test_numeric_comparison_uses_welch_for_two_groups(auth_client):
    analysis_id = upload(auth_client)

    body = compare(auth_client, analysis_id, TWO_GROUPS).json()

    assert body["comparison_type"] == "categorical_numeric"
    assert body["test"]["method"]["key"] == "welch_t_test"
    assert body["rows"]["exclusion_reasons"]["missing_or_non_finite_value"] == 1
    assert [g["count"] for g in body["groups"]] == [4, 4]


def test_numeric_comparison_uses_kruskal_wallis_for_three_groups(auth_client):
    analysis_id = upload(auth_client)

    body = compare(auth_client, analysis_id, THREE_GROUPS).json()

    assert body["test"]["method"]["key"] == "kruskal_wallis"
    assert body["test"]["degrees_of_freedom"] == 2


def test_saved_comparisons_are_listed_and_retrieved_unchanged(auth_client):
    analysis_id = upload(auth_client)
    created = [
        compare(auth_client, analysis_id, body).json()
        for body in (CATEGORICAL, TWO_GROUPS)
    ]

    listed = auth_client.get(f"/api/reports/{analysis_id}/comparisons").json()
    fetched = auth_client.get(
        f"/api/reports/{analysis_id}/comparisons/{created[1]['comparison_id']}"
    ).json()

    assert listed == {"comparisons": created}
    assert fetched == created[1]
    assert fetched["warnings"] == created[1]["warnings"]


def test_unavailable_result_is_saved_not_an_error(auth_client):
    analysis_id = upload(auth_client)
    body = {**CATEGORICAL, "outcome_column": "country"}

    response = compare(auth_client, analysis_id, body)

    assert response.status_code == 201
    test = response.json()["test"]
    assert test["status"] == "unavailable"
    assert "only one category" in test["reason"]
    saved = auth_client.get(f"/api/reports/{analysis_id}/comparisons").json()
    assert saved["comparisons"][0]["test"] == test


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({**CATEGORICAL, "outcome_column": "nope"}, "does not exist"),
        ({**CATEGORICAL, "outcome_column": "age"}, "is numeric"),
        ({**TWO_GROUPS, "value_column": "education"}, "not numeric"),
        ({**TWO_GROUPS, "group_column": "age"}, "is numeric"),
    ],
)
def test_invalid_columns_give_400(auth_client, body, message):
    analysis_id = upload(auth_client)

    response = compare(auth_client, analysis_id, body)

    assert response.status_code == 400
    assert message in response.json()["detail"]
    assert auth_client.get(f"/api/reports/{analysis_id}/comparisons").json() == {
        "comparisons": []
    }


@pytest.mark.parametrize(
    "body",
    [
        {"comparison_type": "paired", "group_column": "a", "value_column": "b"},
        {"comparison_type": "categorical_numeric", "group_column": "income"},
        {"comparison_type": "categorical_categorical", "group_column": "a",
         "value_column": "b"},
    ],
)
def test_malformed_requests_give_422(auth_client, body):
    analysis_id = upload(auth_client)

    assert compare(auth_client, analysis_id, body).status_code == 422


def test_other_users_cannot_compare_list_or_fetch(client):
    register_user(client, email="a@example.com")
    analysis_id = upload(client)
    comparison_id = compare(client, analysis_id, CATEGORICAL).json()["comparison_id"]
    other = TestClient(app)
    register_user(other, email="b@example.com")

    assert compare(other, analysis_id, CATEGORICAL).status_code == 404
    assert other.get(f"/api/reports/{analysis_id}/comparisons").status_code == 404
    assert other.get(
        f"/api/reports/{analysis_id}/comparisons/{comparison_id}"
    ).status_code == 404
    # The owner's saved comparisons are untouched.
    assert len(client.get(f"/api/reports/{analysis_id}/comparisons").json()["comparisons"]) == 1


def test_comparison_must_belong_to_the_requested_report(auth_client):
    first = upload(auth_client)
    second = upload(auth_client)
    comparison_id = compare(auth_client, first, CATEGORICAL).json()["comparison_id"]

    response = auth_client.get(f"/api/reports/{second}/comparisons/{comparison_id}")

    assert response.status_code == 404


def test_unknown_report_gives_404(auth_client):
    assert compare(auth_client, 999, CATEGORICAL).status_code == 404
    assert auth_client.get("/api/reports/999/comparisons").status_code == 404


def test_unauthenticated_requests_are_rejected(client):
    assert compare(client, 1, CATEGORICAL).status_code == 401
    assert client.get("/api/reports/1/comparisons").status_code == 401
    assert client.get("/api/reports/1/comparisons/1").status_code == 401


def test_missing_stored_rows_give_409(auth_client):
    analysis_id = upload(auth_client)
    report = auth_client.get(f"/api/reports/{analysis_id}").json()
    store = app.state.analysis_service.dataset_store
    store.path(report["dataset_id"]).unlink()

    response = compare(auth_client, analysis_id, CATEGORICAL)

    assert response.status_code == 409
    assert "Upload the file again" in response.json()["detail"]


def test_report_includes_category_distributions(auth_client):
    analysis_id = upload(auth_client)
    profiles = auth_client.get(f"/api/reports/{analysis_id}").json()["column_profiles"]

    education = next(p for p in profiles if p["name"] == "education")

    assert education["distribution"]["missing_rows"] == 1
    assert education["distribution"]["categories"][0] == {
        "label": "BA", "count": 3, "percentage": 37.5,
    }


# --- Dataset store ------------------------------------------------------


def test_dataset_store_round_trips_types(tmp_path):
    store = DatasetStore(tmp_path)
    df = pd.DataFrame({
        "label": ["a", None, "c"],
        "count": pd.array([1, None, 3], dtype="Int64"),
        "value": [1.5, 2.5, None],
        "flag": [True, False, True],
    })

    store.save(7, df)

    pd.testing.assert_frame_equal(store.load(7), df)
    assert store.load(8) is None


def test_dataset_store_saves_mixed_type_columns_as_text(tmp_path):
    store = DatasetStore(tmp_path)
    df = pd.DataFrame({"mixed": [1, "two", None, 3.5]})

    store.save(1, df)

    assert store.load(1)["mixed"].tolist() == ["1", "two", None, "3.5"]
    assert list(tmp_path.iterdir()) == [store.path(1)]
