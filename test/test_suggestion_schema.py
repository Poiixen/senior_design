"""The sample suggestion responses must stay valid against the models."""

import json
from pathlib import Path

import pytest

from backend.models.suggestions import SuggestionRequest, SuggestionResponse

SAMPLE_DIR = Path(__file__).parent.parent / "docs" / "examples" / "suggestions"
SAMPLES = sorted(SAMPLE_DIR.glob("*.json"))

EXPECTED_TYPES = {
    "ranked_with_warnings": ["missing_values", "group_difference", "duplicates"],
    "exploratory_comparisons": ["missing_values", "group_difference", "duplicates", "group_difference"],
    "clean_report": [],
    "unavailable_test": ["small_groups"],
    "non_significant": ["group_difference"],
    "ai_source": ["missing_values", "duplicates"],
    "regrouped_comparison": ["group_difference", "regrouping"],
}


@pytest.mark.parametrize("path", SAMPLES, ids=lambda path: path.stem)
def test_sample_matches_models(path):
    sample = json.loads(path.read_text(encoding="utf-8"))
    SuggestionRequest(**sample["request"])
    response = SuggestionResponse(**sample["response"])
    assert response.total_findings >= len(response.suggestions)
    if path.stem in EXPECTED_TYPES:
        assert [s.finding_type for s in response.suggestions] == EXPECTED_TYPES[path.stem]


def test_every_documented_sample_exists():
    assert set(EXPECTED_TYPES) <= {path.stem for path in SAMPLES}


def test_empty_request_is_valid():
    request = SuggestionRequest()
    assert (request.comparison_ids, request.limit, request.offset) == (None, 5, 0)


def accepted_by_the_existing_frontend(body) -> bool:
    """The checks in frontend/app/lib/api.ts (isSuggestionResponse), unchanged by this work."""
    is_strings = lambda items: isinstance(items, list) and all(isinstance(item, str) for item in items)  # noqa: E731
    return (
        isinstance(body.get("analysis_id"), int)
        and body.get("source") in ("ai", "fallback")
        and isinstance(body.get("suggestions"), list)
        and all(
            isinstance(s.get("title"), str)
            and isinstance(s.get("explanation"), str)
            and is_strings(s.get("affected_columns"))
            and is_strings(s.get("evidence"))
            and is_strings(s.get("next_steps"))
            for s in body["suggestions"]
        )
    )


@pytest.mark.parametrize("path", SAMPLES, ids=lambda path: path.stem)
def test_existing_frontend_still_accepts_every_sample(path):
    body = json.loads(path.read_text(encoding="utf-8"))["response"]
    assert accepted_by_the_existing_frontend(body)


@pytest.mark.parametrize("path", SAMPLES, ids=lambda path: path.stem)
def test_every_number_in_the_text_comes_from_the_evidence(path):
    """Numerical claims are backed by saved values, warnings or documented thresholds."""
    from backend.services.suggestions import ai_wording

    documented_thresholds = [0.05, 1, 5, 30, 1.5, 100]
    body = json.loads(path.read_text(encoding="utf-8"))["response"]
    for item in body["suggestions"]:
        material = json.dumps([item["evidence"], item["evidence_values"], item["warnings"], item["priority_reason"]])
        allowed = [number for number, _ in ai_wording._numbers(material)] + documented_thresholds
        text = " ".join([item["title"], item["explanation"], *item["next_steps"]])
        unsupported = [
            number for number, decimals in ai_wording._numbers(text)
            if not ai_wording._numbers_supported(str(number), allowed) and not any(round(number, decimals) == round(k, decimals) for k in allowed)
        ]
        assert not unsupported, (item["finding_id"], unsupported)


def test_samples_carry_no_empty_optional_evidence():
    for path in SAMPLES:
        for item in json.loads(path.read_text(encoding="utf-8"))["response"]["suggestions"]:
            assert "mean_difference_ci" not in item["evidence_values"] or item["evidence_values"]["mean_difference_ci"] is not None
            assert "eta_squared" not in item["evidence_values"] or item["evidence_values"]["eta_squared"] is not None
