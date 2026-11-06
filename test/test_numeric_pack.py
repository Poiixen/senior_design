"""Run the numeric analysis demo pack (Ticket #57) through the API.

The expected values in cases.json come from scripts/build_numeric_pack.py,
which calculates them with pandas and scipy only, so these tests compare the
application with an independent calculation. They also check that saved
results reopen unchanged, that the committed real responses are not stale,
and that the suggestion service (Ticket #47) reads the real results.
"""

import json
from pathlib import Path

import pytest

PACK = Path(__file__).parent.parent / "docs" / "examples" / "numeric-pack"
SPEC = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
CASES = SPEC["cases"]
REL, ABS = SPEC["rel_tolerance"], SPEC["abs_tolerance"]
COMPARISONS = [case for case in CASES if case["kind"] == "comparison"]
PROFILES = [case for case in CASES if case["kind"] == "profile"]


def resolve(document, path):
    for part in path.split("."):
        document = document[int(part)] if isinstance(document, list) else document[part]
    return document


def assert_value(actual, expected, path):
    if isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=REL, abs=ABS), path
    else:
        assert actual == expected, path


def assert_json_matches(actual, expected, path=""):
    if isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=REL, abs=ABS), path
    elif isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert set(actual) == set(expected), path
        for key, value in expected.items():
            next_path = f"{path}.{key}" if path else key
            assert_json_matches(actual[key], value, next_path)
    elif isinstance(expected, list):
        assert isinstance(actual, list), path
        assert len(actual) == len(expected), path
        for index, value in enumerate(expected):
            next_path = f"{path}.{index}" if path else str(index)
            assert_json_matches(actual[index], value, next_path)
    else:
        assert actual == expected, path


def upload(client, dataset):
    csv = (PACK / dataset).read_text(encoding="utf-8")
    response = client.post("/api/analyze", files={"file": (Path(dataset).name, csv, "text/csv")})
    assert response.status_code == 200, response.text
    return response.json()


def strip(response):
    """Drop the fields that depend on which rows happen to be saved."""
    return {
        key: value
        for key, value in response.items()
        if key not in ("comparison_id", "analysis_id", "created_at")
    }


def test_pack_covers_what_the_ticket_asks_for():
    readme = (PACK / "README.md").read_text(encoding="utf-8")
    for case in CASES:
        assert (PACK / case["dataset"]).is_file()
        assert (PACK / "responses" / f"{case['id']}.json").is_file()
        assert f"### {case['id']}" in readme
        assert case["question"] and case["columns"] and case["visual"]
    assert {case["outcome"] for case in CASES} == {"success", "warning", "unavailable"}
    methods = {case["expect"].get("test.method.key") for case in COMPARISONS}
    assert {"welch_t_test", "welch_anova", "kruskal_wallis"} <= methods
    shapes = {case["expect"].get("distribution_shape.classification") for case in PROFILES}
    assert {"right_skewed", "left_skewed", "approximately_symmetric"} <= shapes


@pytest.mark.parametrize("case", COMPARISONS, ids=lambda c: c["id"])
def test_comparison_case_matches_the_independent_calculation(auth_client, case):
    analysis_id = upload(auth_client, case["dataset"])["analysis_id"]
    url = f"/api/reports/{analysis_id}/comparisons"

    response = auth_client.post(url, json=case["request"])

    assert response.status_code == case["expected_status"], response.text
    result = response.json()
    for path, expected in case["expect"].items():
        assert_value(resolve(result, path), expected, path)
    warnings = " ".join(result["warnings"])
    for text in case["expected_warnings_contain"]:
        assert text in warnings, text
    for text in case["expected_absent_warnings"]:
        assert text not in warnings, text
    if case["expected_reason_contains"]:
        assert case["expected_reason_contains"] in result["test"]["reason"]

    # Saved results reopen unchanged, with their method and chart evidence.
    listed = auth_client.get(url).json()["comparisons"]
    fetched = auth_client.get(f"{url}/{result['comparison_id']}").json()
    assert listed == [result] and fetched == result


@pytest.mark.parametrize("case", PROFILES, ids=lambda c: c["id"])
def test_profile_case_matches_the_independent_calculation(auth_client, case):
    report = upload(auth_client, case["dataset"])
    column = case["columns"]["column"]

    profile = next(p for p in report["column_profiles"] if p["name"] == column)

    for path, expected in case["expect"].items():
        assert_value(resolve(profile, path), expected, path)
    shape = profile["distribution_shape"]
    if case["expected_reason_contains"]:
        assert case["expected_reason_contains"] in shape["reason"]
    assert bool(shape["warnings"]) == case.get("expects_shape_warning", False)
    # The saved report returns the same description.
    saved = auth_client.get(f"/api/reports/{report['analysis_id']}").json()
    assert next(p for p in saved["column_profiles"] if p["name"] == column) == profile


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_committed_response_matches_the_endpoint(auth_client, case):
    example = json.loads((PACK / "responses" / f"{case['id']}.json").read_text(encoding="utf-8"))
    report = upload(auth_client, case["dataset"])

    if case["kind"] == "profile":
        actual = next(p for p in report["column_profiles"] if p["name"] == case["columns"]["column"])
        assert actual == example["response"]
        return
    response = auth_client.post(
        f"/api/reports/{report['analysis_id']}/comparisons", json=example["request"]
    )
    assert response.status_code == example["status"]
    assert_json_matches(strip(response.json()), strip(example["response"]))


def by_id(case_id):
    return next(case for case in CASES if case["id"] == case_id)


def suggestions_for(client, case_id):
    case = by_id(case_id)
    analysis_id = upload(client, case["dataset"])["analysis_id"]
    if case["request"]:
        assert client.post(
            f"/api/reports/{analysis_id}/comparisons", json=case["request"]
        ).status_code == 201
    response = client.post(f"/api/reports/{analysis_id}/suggestions", json={})
    assert response.status_code == 200, response.text
    return response.json()


def group_finding(body):
    return next(s for s in body["suggestions"] if s["finding_type"] == "group_difference")


def test_suggestions_explain_real_anova_results(auth_client):
    body = suggestions_for(auth_client, "anova_unequal_groups")

    finding = group_finding(body)
    values = finding["evidence_values"]
    assert values["method_key"] == "welch_anova"
    assert values["comparison_basis"] == "means"
    assert values["eta_squared"] == pytest.approx(by_id("anova_unequal_groups")["expect"]["test.eta_squared"])
    assert "anova" not in body["unavailable_analyses"]
    assert "does not say which groups differ" in finding["explanation"]
    visual = finding["visual"]
    assert visual["chart_type"] == "grouped_box" and visual["unavailable_fields"] == []


def test_suggestions_show_the_welch_confidence_interval(auth_client):
    body = suggestions_for(auth_client, "two_groups_known_difference")

    values = group_finding(body)["evidence_values"]
    expect = by_id("two_groups_known_difference")["expect"]
    assert values["mean_difference_ci"]["lower"] == pytest.approx(expect["test.mean_difference_ci.lower"])
    assert values["mean_difference_ci"]["level"] == 0.95


def test_suggestions_read_real_distribution_shapes(auth_client):
    body = suggestions_for(auth_client, "shape_right_skewed")

    skewed = {s["affected_columns"][0] for s in body["suggestions"] if s["finding_type"] == "skewed_distribution"}
    assert skewed == {"right_skewed", "left_skewed"}
