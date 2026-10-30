"""Ticket #58: identifier review, user-defined regrouping and its guarantees."""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.diagnostics.category_regrouping import label_key, regroup_columns
from backend.diagnostics.comparison_common import ComparisonError
from backend.diagnostics.identifier_detection import review_identifier_column
from conftest import register_user

CSV = (
    "education,income,age\n"
    + "".join(f"HS,{'high' if i % 3 == 0 else 'low'},{30 + i}\n" for i in range(12))
    + "".join(f"BA,{'high' if i % 2 == 0 else 'low'},{35 + i}\n" for i in range(10))
    + "MA,high,50\nMA,low,52\nPhD,high,60\n?,low,41\nBA,high,\n"
)
DEGREE = [{"label": "Degree", "categories": ["BA", "MA", "PhD"]}]


def upload(client):
    response = client.post("/api/analyze", files={"file": ("people.csv", CSV, "text/csv")})
    assert response.status_code == 200
    return response.json()["analysis_id"]


def compare(client, analysis_id, **extra):
    body = {"comparison_type": "categorical_categorical", "group_column": "education", "outcome_column": "income", **extra}
    return client.post(f"/api/reports/{analysis_id}/comparisons", json=body)


def stored_frame(analysis_id):
    service = app.state.analysis_service
    dataset_id = service.get_report(analysis_id)["dataset_id"]
    return service.dataset_store.load(dataset_id)


# --- guarantees ---------------------------------------------------------------------


def test_regrouping_leaves_the_stored_dataset_and_earlier_comparisons_unchanged(auth_client):
    analysis_id = upload(auth_client)
    original = compare(auth_client, analysis_id).json()
    before_rows = stored_frame(analysis_id).copy()
    report_before = auth_client.get(f"/api/reports/{analysis_id}").json()

    regrouped = compare(auth_client, analysis_id, category_mappings={"education": DEGREE}).json()

    pd.testing.assert_frame_equal(stored_frame(analysis_id), before_rows)
    assert auth_client.get(f"/api/reports/{analysis_id}").json() == report_before
    listed = auth_client.get(f"/api/reports/{analysis_id}/comparisons").json()["comparisons"]
    assert listed[0] == original and "regrouping" not in original
    assert regrouped["comparison_id"] != original["comparison_id"]
    assert regrouped["regrouping"]["original_comparison_id"] == original["comparison_id"]
    assert regrouped["regrouping"]["analysis_id"] == analysis_id
    assert regrouped["regrouping"]["dataset_id"] == report_before["dataset_id"]


def test_requests_without_mappings_are_unchanged(auth_client):
    analysis_id = upload(auth_client)
    for extra in ({}, {"category_mappings": None}, {"category_mappings": {}}):
        result = compare(auth_client, analysis_id, **extra).json()
        assert "regrouping" not in result


def test_regrouped_counts_cover_the_same_rows_and_keep_missing_values(auth_client):
    analysis_id = upload(auth_client)
    column = compare(auth_client, analysis_id, category_mappings={"education": DEGREE}).json()[
        "regrouping"
    ]["columns"][0]
    assert sum(c["count"] for c in column["before"]) == sum(c["count"] for c in column["after"])
    assert column["missing_values"] == column["missing_values_after"] == 1
    assert {c["label"]: c["count"] for c in column["after"]} == {"Degree": 14, "HS": 12}
    assert column["unmapped_categories"] == 1 and column["count_denominator"] == "non-missing rows"


def test_regrouped_result_is_distinguishable_and_explains_its_limits(auth_client):
    analysis_id = upload(auth_client)
    result = compare(auth_client, analysis_id, category_mappings={"education": DEGREE}).json()
    assert result["regrouping"]["applied"] is True
    assert "do not show that the regrouped comparison is more valid" in result["regrouping"]["note"]
    assert result["group_categories"] == ["Degree", "HS"] or result["group_categories"] == ["HS", "Degree"]


def test_numeric_regrouping_records_a_method_change(auth_client):
    analysis_id = upload(auth_client)
    body = {"comparison_type": "categorical_numeric", "group_column": "education", "value_column": "age",
            "category_mappings": {"education": DEGREE}}
    change = auth_client.post(f"/api/reports/{analysis_id}/comparisons", json=body).json()["regrouping"]["method_change"]
    assert (change["group_count_before"], change["group_count_after"]) == (4, 2)
    assert change["method_before"] == "kruskal_wallis" and change["method_after"] == "welch_t_test"
    assert change["changed"] and "different questions" in change["explanation"]


def test_categorical_results_include_expected_count_details(auth_client):
    analysis_id = upload(auth_client)
    summary = compare(auth_client, analysis_id).json()["test"]["expected_count_summary"]
    assert set(summary) >= {"cells", "cells_below_5", "cells_below_1", "share_below_5", "meets_guideline"}
    assert summary["cells_below_5"] > 0 and summary["meets_guideline"] is False


# --- ownership -------------------------------------------------------------------------


def test_other_users_cannot_regroup_a_report(client):
    register_user(client, email="a@example.com")
    analysis_id = upload(client)
    other = TestClient(app)
    register_user(other, email="b@example.com")
    assert compare(other, analysis_id, category_mappings={"education": DEGREE}).status_code == 404
    assert client.get(f"/api/reports/{analysis_id}/comparisons").json()["comparisons"] == []


# --- validation through the API -------------------------------------------------------------


@pytest.mark.parametrize(
    ("mapping", "needle"),
    [
        ({"education": [{"label": "X", "categories": []}]}, "lists no categories"),
        ({"education": [{"label": "X", "categories": ["BA"]}, {"label": "X", "categories": ["MA"]}]}, "more than one combination"),
        ({"education": [{"label": "X", "categories": ["BA", "BA"]}]}, "listed twice"),
        ({"education": [{"label": "BA", "categories": ["MA", "PhD"]}]}, "collides"),
        ({"education": []}, "at least one combination"),
        ({"income": [{"label": "x", "categories": ["nope"]}]}, "does not exist"),
        ({"age": [{"label": "x", "categories": ["a"]}]}, "not one of them"),
    ],
)
def test_invalid_mappings_give_400_and_save_nothing(auth_client, mapping, needle):
    analysis_id = upload(auth_client)
    response = compare(auth_client, analysis_id, category_mappings=mapping)
    assert response.status_code == 400 and needle in response.json()["detail"]
    assert auth_client.get(f"/api/reports/{analysis_id}/comparisons").json()["comparisons"] == []


def test_a_label_may_reuse_a_member_of_its_own_combination(auth_client):
    analysis_id = upload(auth_client)
    mapping = {"education": [{"label": "BA", "categories": ["BA", "MA", "PhD"]}]}
    assert compare(auth_client, analysis_id, category_mappings=mapping).status_code == 201


def test_malformed_mappings_give_422(auth_client):
    analysis_id = upload(auth_client)
    for mapping in ({"education": "Degree"}, {"education": [{"label": "X"}]}, {"education": [{"categories": ["BA"]}]}):
        assert compare(auth_client, analysis_id, category_mappings=mapping).status_code == 422


def test_group_count_limits_still_apply_after_regrouping():
    df = pd.DataFrame({"g": [f"c{i}" for i in range(150)] * 2, "v": range(300)})
    from backend.diagnostics.numeric_group_comparison import compare_numeric_across_groups

    working, _ = regroup_columns(df, {"g": "group"}, {"g": [{"label": "x", "categories": ["c0", "c1"]}]}, ("v",))
    result = compare_numeric_across_groups(working, "g", "v")
    assert result["status"] == "unavailable" and "at most 100" in result["reason"]


# --- regrouping unit behaviour ---------------------------------------------------------------


def test_label_types_are_distinct():
    assert len({label_key(1), label_key("1"), label_key(True), label_key(1.0)}) == 4


def test_numbers_text_and_booleans_with_the_same_look_are_different_categories():
    df = pd.DataFrame({"g": pd.Series([1, "1", True, "x", None, "x"], dtype=object), "v": range(6)})
    working, evidence = regroup_columns(df, {"g": "group"}, {"g": [{"label": "one-text", "categories": ["1"]}]}, ("v",))
    assert list(working["g"])[:4] == [1, "one-text", True, "x"]
    assert pd.isna(working["g"][4]) and evidence[0]["missing_values_after"] == 1
    with pytest.raises(ComparisonError, match=r"1 \(int\)"):
        regroup_columns(df, {"g": "group"}, {"g": [{"label": "n", "categories": [1, 1]}]}, ("v",))
    with pytest.raises(ComparisonError, match=r"2 \(int\) does not exist"):
        regroup_columns(df, {"g": "group"}, {"g": [{"label": "n", "categories": [2]}]}, ("v",))


def test_source_frame_is_never_modified():
    df = pd.DataFrame({"g": ["a", "b", "c", "a"], "v": [1.0, 2.0, 3.0, 4.0]})
    snapshot = df.copy(deep=True)
    working, _ = regroup_columns(df, {"g": "group"}, {"g": [{"label": "ab", "categories": ["a", "b"]}]}, ("v",))
    pd.testing.assert_frame_equal(df, snapshot)
    assert list(working["g"]) == ["ab", "ab", "c", "ab"]


# --- identifier review ---------------------------------------------------------------------


def review(name, values):
    return review_identifier_column(name, pd.Series(values))


def test_unique_text_values_are_flagged_with_their_evidence():
    result = review("anything", [f"x{i}" for i in range(20)])
    assert result["likely_identifier"]
    assert "20 of 20 non-missing values are distinct" in result["reasons"][0]
    assert result["signals"]["distinct_ratio"] == 1.0 and "not a classification" in result["note"]


def test_name_alone_and_high_cardinality_alone_are_not_flagged():
    assert not review("region_id", ["a", "b", "c", "d"] * 10)["likely_identifier"]
    assert not review("city", [f"c{i % 12}" for i in range(120)])["likely_identifier"]


def test_name_with_mostly_distinct_values_is_flagged_and_names_the_word():
    values = [f"k{i // 1}" for i in range(15)] + [f"k{i}" for i in range(5)]
    result = review("userId", values)
    assert result["likely_identifier"] and result["signals"]["name_words"] == ["id"]


def test_small_columns_are_not_judged():
    assert not review("customer_id", ["a", "b", "c"])["likely_identifier"]


def test_numeric_measurements_are_not_candidates_but_integer_ids_are():
    assert review_identifier_column("price", pd.Series(np.linspace(0, 1, 50))) is None
    assert review_identifier_column("amount", pd.Series(range(50))) is None
    assert review_identifier_column("order_id", pd.Series(range(50)))["likely_identifier"]


def test_words_such_as_paid_or_valid_do_not_match():
    assert not review("paid", [f"x{i}" for i in range(12)] * 1 + ["x0"])["signals"]["name_words"]
    assert review("valid_flag", ["y", "n"] * 10)["signals"]["name_words"] == []


def test_flag_is_a_warning_not_a_block_and_can_be_confirmed(auth_client):
    csv = "uid,grp,score\n" + "".join(f"u{i},{'a' if i % 2 else 'b'},{i}\n" for i in range(30))
    analysis_id = auth_client.post("/api/analyze", files={"file": ("d.csv", csv, "text/csv")}).json()["analysis_id"]
    body = {"comparison_type": "categorical_numeric", "group_column": "uid", "value_column": "score"}
    url = f"/api/reports/{analysis_id}/comparisons"

    flagged = auth_client.post(url, json=body)
    confirmed = auth_client.post(url, json={**body, "confirm_columns": ["uid"]})

    assert flagged.status_code == confirmed.status_code == 201
    assert any("may be an identifier" in w for w in flagged.json()["warnings"])
    assert not any("may be an identifier" in w for w in confirmed.json()["warnings"])
    assert confirmed.json()["identifier_review"][0]["reasons"] == flagged.json()["identifier_review"][0]["reasons"]
    stray = auth_client.post(url, json={**body, "confirm_columns": ["score"]})
    assert stray.status_code == 400 and "cannot be confirmed" in stray.json()["detail"]


def test_flagged_columns_appear_in_the_saved_report_profile(auth_client):
    csv = "uid,score\n" + "".join(f"u{i},{i}\n" for i in range(20))
    report = auth_client.post("/api/analyze", files={"file": ("d.csv", csv, "text/csv")}).json()
    profiles = {p["name"]: p for p in report["column_profiles"]}
    assert profiles["uid"]["identifier_review"]["likely_identifier"]
    assert "identifier_review" not in profiles["score"]


# --- invalid selections are rejected before anything is regrouped --------------------------


@pytest.mark.parametrize(
    ("body", "needle"),
    [
        ({"group_column": "nope", "outcome_column": "income"}, "does not exist"),
        ({"group_column": "education", "outcome_column": "nope"}, "does not exist"),
        ({"group_column": "age", "outcome_column": "income"}, "numeric"),
        ({"group_column": "education", "outcome_column": "education"}, "two different columns"),
    ],
)
def test_mappings_on_an_invalid_selection_give_400_not_500(auth_client, body, needle):
    analysis_id = upload(auth_client)
    mapping = {body["group_column"]: [{"label": "X", "categories": ["BA"]}]}
    response = compare(auth_client, analysis_id, category_mappings=mapping, **body)
    assert response.status_code == 400 and needle in response.json()["detail"]
    assert auth_client.get(f"/api/reports/{analysis_id}/comparisons").json()["comparisons"] == []


def test_a_missing_measurement_column_with_a_mapping_gives_400(auth_client):
    analysis_id = upload(auth_client)
    response = auth_client.post(f"/api/reports/{analysis_id}/comparisons", json={
        "comparison_type": "categorical_numeric", "group_column": "education", "value_column": "nope",
        "category_mappings": {"education": DEGREE}})
    assert response.status_code == 400 and "does not exist" in response.json()["detail"]


# --- limits are checked after regrouping -------------------------------------------------


def wide_csv(groups: int, outcomes: int, rows: int) -> str:
    lines = ["g,o"]
    for i in range(rows):
        lines.append(f"g{i % groups:03d},o{(i * 7 + i // groups) % outcomes:03d}")
    return "\n".join(lines) + "\n"


def test_category_limit_is_applied_to_the_regrouped_column(auth_client):
    csv = wide_csv(groups=120, outcomes=3, rows=480)
    analysis_id = auth_client.post("/api/analyze", files={"file": ("w.csv", csv, "text/csv")}).json()["analysis_id"]
    base = {"comparison_type": "categorical_categorical", "group_column": "g", "outcome_column": "o"}
    url = f"/api/reports/{analysis_id}/comparisons"

    too_many = auth_client.post(url, json=base).json()
    merged = [{"label": "rest", "categories": [f"g{i:03d}" for i in range(40, 120)]}]
    fewer = auth_client.post(url, json={**base, "category_mappings": {"g": merged}}).json()

    assert too_many["status"] == "unavailable" and "at most 100" in too_many["reason"]
    assert fewer["status"] == "ok" and len(fewer["group_categories"]) == 41
    assert fewer["regrouping"]["columns"][0]["categories_before"] == 120
    assert fewer["regrouping"]["columns"][0]["categories_after"] == 41


def test_large_table_warning_is_recalculated_after_regrouping(auth_client):
    csv = wide_csv(groups=60, outcomes=60, rows=1200)
    analysis_id = auth_client.post("/api/analyze", files={"file": ("w.csv", csv, "text/csv")}).json()["analysis_id"]
    base = {"comparison_type": "categorical_categorical", "group_column": "g", "outcome_column": "o"}
    url = f"/api/reports/{analysis_id}/comparisons"

    large = auth_client.post(url, json=base).json()
    merged = [{"label": "rest", "categories": [f"g{i:03d}" for i in range(20, 60)]}]
    smaller = auth_client.post(url, json={**base, "category_mappings": {"g": merged}}).json()

    assert any("large contingency table" in w for w in large["warnings"])
    assert not any("large contingency table" in w for w in smaller["warnings"])
    assert len(smaller["group_categories"]) * len(smaller["outcome_categories"]) < 2500


def test_regrouping_does_not_raise_the_limits(auth_client):
    csv = wide_csv(groups=150, outcomes=3, rows=600)
    analysis_id = auth_client.post("/api/analyze", files={"file": ("w.csv", csv, "text/csv")}).json()["analysis_id"]
    merged = [{"label": "rest", "categories": ["g000", "g001"]}]
    result = compare(auth_client, analysis_id, group_column="g", outcome_column="o", category_mappings={"g": merged}).json()
    assert result["status"] == "unavailable" and "at most 100" in result["reason"]
