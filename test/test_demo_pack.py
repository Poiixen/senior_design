"""Run the shared demo pack (Ticket #58) through the API.

The expected values in cases.json come from scripts/build_demo_pack.py, which
calculates them with pandas and scipy only, so these tests compare the
application with an independent calculation. They also check that saved
results reopen unchanged.
"""

import json
import math
from pathlib import Path

import pytest

PACK = Path(__file__).parent.parent / "docs" / "examples" / "demo-pack"
SPEC = json.loads((PACK / "cases.json").read_text(encoding="utf-8"))
CASES = SPEC["cases"]
REL, ABS = SPEC["rel_tolerance"], SPEC["abs_tolerance"]


def resolve(document, path):
    for part in path.split("."):
        document = document[int(part)] if isinstance(document, list) else document[part]
    return document


def assert_value(actual, expected, path):
    if isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=REL, abs=ABS), path
    else:
        assert actual == expected, path


def upload(client, dataset):
    csv = (PACK / dataset).read_text(encoding="utf-8")
    response = client.post("/api/analyze", files={"file": (Path(dataset).name, csv, "text/csv")})
    assert response.status_code == 200, response.text
    return response.json()


def test_pack_files_are_present_and_documented():
    assert len(CASES) >= 10
    readme = (PACK / "README.md").read_text(encoding="utf-8")
    for case in CASES:
        assert (PACK / case["dataset"]).is_file()
        assert f"## {case['id']}" in readme
    assert {case["ticket"] for case in CASES} == {58}


@pytest.mark.parametrize("case", [c for c in CASES if c["request"]], ids=lambda c: c["id"])
def test_comparison_case_matches_the_independent_calculation(auth_client, case):
    analysis_id = upload(auth_client, case["dataset"])["analysis_id"]
    url = f"/api/reports/{analysis_id}/comparisons"

    response = auth_client.post(url, json=case["request"])

    assert response.status_code == case["expected_status"], response.text
    if case["expected_status"] != 201:
        assert case["expected_detail_contains"] in response.json()["detail"]
        assert auth_client.get(url).json()["comparisons"] == []
        return

    result = response.json()
    for path, expected in case["expect"].items():
        assert_value(resolve(result, path), expected, path)
    warnings = " ".join(result["warnings"])
    for text in case.get("expected_warnings_contain", []):
        assert text in warnings, text
    for text in case.get("expected_absent_warnings", []):
        assert text not in warnings, text
    for key in case.get("expected_absent_keys", []):
        assert key not in result

    if "expect_counts" in case:
        column = result["regrouping"]["columns"][0]
        assert column["before"] == case["expect_counts"]["before"]
        assert column["after"] == case["expect_counts"]["after"]
        assert sum(item["count"] for item in column["after"]) == sum(
            item["count"] for item in column["before"]
        )
    if "expect_mapping" in case:
        assert result["regrouping"]["mappings"] == case["expect_mapping"]

    # Saved results reopen unchanged, with their method and mapping.
    listed = auth_client.get(url).json()["comparisons"]
    fetched = auth_client.get(f"{url}/{result['comparison_id']}").json()
    assert listed == [result] and fetched == result


def test_every_pack_dataset_can_be_uploaded(auth_client):
    for dataset in sorted({c["dataset"] for c in CASES}):
        assert upload(auth_client, dataset)["status"] == "completed", dataset
    assert not math.isnan(len(CASES))
