"""The saved Ticket #58 example responses must match what the endpoint returns now."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
EXAMPLES = sorted((ROOT / "docs" / "examples" / "regrouping").glob("*.json"))


def strip(response):
    """Drop the fields that depend on which rows happen to be saved, not on the feature."""
    result = json.loads(json.dumps(response))
    for key in ("comparison_id", "analysis_id", "created_at"):
        result.pop(key, None)
    regrouping = result.get("regrouping")
    if regrouping:
        regrouping.pop("analysis_id", None)
        regrouping.pop("dataset_id", None)
        regrouping["original_comparison_id"] = regrouping["original_comparison_id"] is not None
    return result


def test_examples_exist():
    names = {path.stem for path in EXAMPLES}
    assert {"identifier_warning", "identifier_confirmed", "sparse_comparison", "valid_combination",
            "regrouped_with_remaining_warnings", "method_change", "invalid_label_collision"} <= names


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda path: path.stem)
def test_example_matches_the_endpoint(auth_client, path):
    example = json.loads(path.read_text(encoding="utf-8"))
    csv = (ROOT / example["dataset"]).read_text(encoding="utf-8")
    report = auth_client.post("/api/analyze", files={"file": (Path(example["dataset"]).name, csv, "text/csv")}).json()
    url = f"/api/reports/{report['analysis_id']}/comparisons"
    for earlier in example["earlier_requests"]:
        assert auth_client.post(url, json=earlier).status_code == 201

    response = auth_client.post(url, json=example["request"])

    assert response.status_code == example["status"]
    assert strip(response.json()) == strip(example["response"])


def test_examples_show_what_the_ticket_asks_for():
    by_name = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in EXAMPLES}
    valid = by_name["valid_combination"]["response"]["regrouping"]
    assert valid["original_comparison_id"] is not None
    column = valid["columns"][0]
    assert column["before"] and column["after"] and valid["mappings"]["education"]
    assert by_name["method_change"]["response"]["regrouping"]["method_change"]["changed"] is True
    assert any("expected counts below 5" in w for w in by_name["regrouped_with_remaining_warnings"]["response"]["warnings"])
    assert by_name["identifier_warning"]["response"]["identifier_review"][0]["reasons"]
    assert by_name["invalid_label_collision"]["status"] == 400
