"""Tests for the Ticket #52 research prototype (not a production diagnostic).

Needs the Ticket #46 comparisons from PR #94.
"""

import numpy as np
import pandas as pd
import pytest

from backend.diagnostics.categorical_comparison import compare_categorical
from research.demographic_regression_prototype import (
    MISSING_GROUP_LABEL,
    fit_logistic_example,
    make_synthetic_dataset,
    outcome_rate_by_group,
    wilson_interval,
)


def _by_group(report):
    return {g["group"]: g for g in report["groups"]}


def test_rates_differences_and_ratios_by_hand():
    df = pd.DataFrame(
        {
            "g": ["A"] * 10 + ["B"] * 10,
            "y": [1] * 5 + [0] * 5 + [1] * 2 + [0] * 8,
        }
    )

    report = outcome_rate_by_group(df, "g", "y", reference_group="A", min_group_size=1)
    groups = _by_group(report)

    assert groups["A"]["rate"] == pytest.approx(50.0)
    assert groups["B"]["rate"] == pytest.approx(20.0)
    assert groups["B"]["difference_vs_reference_pp"] == pytest.approx(-30.0)
    assert groups["B"]["ratio_vs_reference"] == pytest.approx(0.4)
    assert groups["A"]["is_reference"]


def test_missing_outcome_excluded_and_missing_group_kept():
    df = pd.DataFrame(
        {
            "g": ["A", "A", "A", None, None, "B"],
            "y": [1, 0, np.nan, 1, 1, 0],
        }
    )

    report = outcome_rate_by_group(df, "g", "y", reference_group="A", min_group_size=1)
    groups = _by_group(report)

    assert report["excluded_missing_outcome"] == 1
    assert report["rows_with_missing_group"] == 2
    assert groups[MISSING_GROUP_LABEL]["n"] == 2
    assert groups[MISSING_GROUP_LABEL]["is_missing_group"]
    assert groups["A"]["n"] == 2


def test_small_groups_are_flagged_not_dropped():
    df = pd.DataFrame({"g": ["A"] * 40 + ["B"] * 5, "y": [1, 0] * 20 + [1] * 5})

    groups = _by_group(outcome_rate_by_group(df, "g", "y", reference_group="A"))

    assert groups["B"]["small_group"]
    assert groups["B"]["rate"] == pytest.approx(100.0)
    assert not groups["A"]["small_group"]


def test_zero_reference_rate_gives_no_ratio():
    df = pd.DataFrame({"g": ["A", "A", "B", "B"], "y": [0, 0, 1, 0]})

    groups = _by_group(outcome_rate_by_group(df, "g", "y", reference_group="A", min_group_size=1))

    assert groups["B"]["ratio_vs_reference"] is None


def test_unknown_reference_group_raises():
    df = pd.DataFrame({"g": ["A", "B"], "y": [1, 0]})

    with pytest.raises(ValueError):
        outcome_rate_by_group(df, "g", "y", reference_group="Z")


def test_non_binary_outcome_raises():
    df = pd.DataFrame({"g": ["A", "A", "B"], "y": ["x", "y", "z"]})

    with pytest.raises(ValueError, match="binary"):
        outcome_rate_by_group(df, "g", "y", reference_group="A", positive_value="x")


def test_rates_match_ticket_46_row_percentages():
    df = make_synthetic_dataset()
    report = outcome_rate_by_group(df, "group", "high_income", reference_group="Group A")
    comparison = compare_categorical(
        df.assign(high_income=df["high_income"].astype(object)), "group", "high_income"
    )
    positive = comparison["outcome_categories"].index(1)

    groups = _by_group(report)
    for label, row in zip(comparison["group_categories"], comparison["row_percentages"]):
        assert groups[label]["rate"] == pytest.approx(row[positive], abs=0.005)
    assert report["independence_test"]["rows_included"] == comparison["rows"]["included"]
    assert report["independence_test"]["p_value"] == pytest.approx(comparison["test"]["p_value"])


def test_independence_test_unavailable_with_one_recorded_group():
    df = pd.DataFrame({"g": ["A", "A", None], "y": [1, 0, 1]})

    report = outcome_rate_by_group(df, "g", "y", reference_group="A", min_group_size=1)

    assert report["independence_test"]["status"] == "unavailable"
    assert report["independence_test"]["p_value"] is None


def test_wilson_interval_contains_estimate_and_handles_empty():
    low, high = wilson_interval(5, 10)

    assert low < 0.5 < high
    assert wilson_interval(0, 0) == (None, None)
    assert wilson_interval(0, 10)[0] == 0.0


def test_synthetic_dataset_is_deterministic():
    pd.testing.assert_frame_equal(make_synthetic_dataset(), make_synthetic_dataset())


def test_logistic_example_is_reproducible_and_flags_correlation():
    df = make_synthetic_dataset()
    kwargs = dict(
        outcome_column="high_income",
        numeric_predictors=["age", "education_years", "hours_per_week", "overtime_hours"],
        nominal_predictors={"sector": "Private", "group": "Group A"},
        group_column="group",
    )

    first = fit_logistic_example(df, **kwargs)
    second = fit_logistic_example(df, **kwargs)

    assert first == second
    assert first["evaluation"]["roc_auc"] > 0.6
    review = first["predictor_review"]
    flagged_pairs = [set(item["pair"]) for item in review["numeric_pairs"]]
    assert {"hours_per_week", "overtime_hours"} in flagged_pairs
    # sector and group are independent by construction.
    assert [item["pair"] for item in review["nominal_pairs"]] == [["sector", "group"]]
    assert not review["nominal_pairs"][0]["flagged"]
    # Group B was generated with fewer hours; the #46 numeric comparison shows it.
    hours = next(i for i in review["numeric_by_group"] if i["value_column"] == "hours_per_week")
    assert hours["group_means"]["Group B"] < hours["group_means"]["Group A"] - 3
    features = {c["feature"] for c in first["coefficients"]}
    # Reference levels are dropped; the correlated predictor is not.
    assert "sector_Private" not in features
    assert "group_Group A" not in features
    assert "overtime_hours" in features
