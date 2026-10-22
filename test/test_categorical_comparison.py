"""Category breakdowns and categorical-vs-categorical comparisons."""

from math import sqrt

import numpy as np
import pandas as pd
import pytest
from scipy.stats import chi2_contingency

from backend.diagnostics import categorical_comparison
from backend.diagnostics.categorical_comparison import (
    category_distribution,
    compare_categorical,
)
from backend.diagnostics.comparison_common import ComparisonError
from backend.diagnostics.generic_dataset_profiler import profile_dataset


def table_df(cells: dict) -> pd.DataFrame:
    """Expand {(group, outcome): count} into one row per observation."""
    rows = [pair for pair, count in cells.items() for _ in range(count)]
    return pd.DataFrame(rows, columns=["group", "outcome"])


# --- Category distributions ---------------------------------------------


def test_distribution_counts_and_percentages_use_non_missing_rows():
    column = pd.Series(["b", "a", "b", None, "c", "b", "a", None])

    result = category_distribution(column)

    assert result["distinct_categories"] == 3
    assert result["total_rows"] == 8
    assert result["non_missing_rows"] == 6
    assert result["missing_rows"] == 2
    assert result["percentage_denominator"] == "non_missing_rows"
    assert result["categories"] == [
        {"label": "b", "count": 3, "percentage": 50.0},
        {"label": "a", "count": 2, "percentage": 33.33},
        {"label": "c", "count": 1, "percentage": 16.67},
    ]
    assert result["categories_truncated"] is False


def test_distribution_breaks_count_ties_by_label():
    result = category_distribution(pd.Series(["z", "m", "a", "m", "a"]))

    assert [c["label"] for c in result["categories"]] == ["a", "m", "z"]


def test_distribution_reports_categories_beyond_the_limit(monkeypatch):
    monkeypatch.setattr(categorical_comparison, "MAX_PROFILE_CATEGORIES", 2)

    result = category_distribution(pd.Series(["a", "a", "a", "b", "b", "c", "d"]))

    assert [c["label"] for c in result["categories"]] == ["a", "b"]
    assert result["distinct_categories"] == 4
    assert result["categories_truncated"] is True
    assert result["omitted_categories"] == 2
    assert result["omitted_count"] == 2


def test_distribution_of_all_missing_column():
    result = category_distribution(pd.Series([None, None], dtype=object))

    assert result["distinct_categories"] == 0
    assert result["categories"] == []
    assert result["missing_rows"] == 2


def test_profile_adds_distribution_and_keeps_existing_fields(simple_clean_df):
    profile = profile_dataset(simple_clean_df)
    group = next(d for d in profile["column_details"] if d["name"] == "group")
    score = next(d for d in profile["column_details"] if d["name"] == "score")

    assert group["most_common_count"] == 2
    assert group["most_common_percentage"] == pytest.approx(33.33)
    assert group["distribution"]["distinct_categories"] == 3
    assert sum(c["count"] for c in group["distribution"]["categories"]) == 6
    assert "distribution" not in score


# --- Comparisons --------------------------------------------------------


def test_known_table_matches_hand_calculation():
    df = table_df({("A", "x"): 10, ("A", "y"): 20, ("B", "x"): 30, ("B", "y"): 40})

    result = compare_categorical(df, "group", "outcome")

    # Largest categories first: B (70) before A (30), y (60) before x (40).
    assert result["group_categories"] == ["B", "A"]
    assert result["outcome_categories"] == ["y", "x"]
    assert result["counts"] == [[40, 30], [20, 10]]
    assert result["group_totals"] == [70, 30]
    assert result["outcome_totals"] == [60, 40]
    assert result["row_percentages"] == [[57.14, 42.86], [66.67, 33.33]]
    assert result["percentage_denominator"] == "group_total"

    # Expected counts 42/28/18/12; each cell is 4 away from expected.
    chi_square = 4 / 42 + 4 / 28 + 4 / 18 + 4 / 12
    test = result["test"]
    assert test["status"] == "ok"
    assert test["method"]["key"] == "chi_square_independence"
    assert test["statistic"] == pytest.approx(chi_square)
    assert test["degrees_of_freedom"] == 1
    assert test["expected_counts"] == [[42.0, 28.0], [18.0, 12.0]]
    assert result["association"]["value"] == pytest.approx(sqrt(chi_square / 100))
    assert result["warnings"] == []


def test_statistics_match_scipy_on_a_larger_table():
    df = table_df({
        ("HS", "<=50K"): 50, ("HS", ">50K"): 10,
        ("BA", "<=50K"): 30, ("BA", ">50K"): 25,
        ("MA", "<=50K"): 8, ("MA", ">50K"): 17,
    })

    result = compare_categorical(df, "group", "outcome")
    table = np.array(result["counts"])
    statistic, p_value, dof, _ = chi2_contingency(table, correction=False)

    assert result["test"]["statistic"] == pytest.approx(statistic)
    assert result["test"]["p_value"] == pytest.approx(p_value)
    assert result["test"]["degrees_of_freedom"] == dof == 2
    assert result["association"]["value"] == pytest.approx(
        sqrt(statistic / (table.sum() * 1))
    )


def test_rows_missing_either_value_are_excluded_and_counted():
    df = pd.DataFrame({
        "group": ["a", "a", "b", "b", None, None, "b"],
        "outcome": ["x", "y", "x", "y", "x", None, None],
    })

    result = compare_categorical(df, "group", "outcome")

    assert result["rows"] == {
        "total": 7,
        "included": 4,
        "excluded": 3,
        "exclusion_reasons": {"missing_group_value": 2, "missing_outcome_value": 2},
    }
    assert np.array(result["counts"]).sum() == 4


def test_one_category_gives_table_but_unavailable_test():
    df = pd.DataFrame({"group": ["a", "b", "a"], "outcome": ["x", "x", "x"]})

    result = compare_categorical(df, "group", "outcome")

    assert result["status"] == "ok"
    assert result["counts"] == [[2], [1]]
    assert result["test"]["status"] == "unavailable"
    assert "only one category" in result["test"]["reason"]
    assert result["association"]["status"] == "unavailable"


def test_no_complete_rows_is_unavailable():
    df = pd.DataFrame({"group": ["a", None], "outcome": [None, "x"]})

    result = compare_categorical(df, "group", "outcome")

    assert result["status"] == "unavailable"
    assert result["reason"] == "No rows have values in both selected columns."
    assert result["counts"] == []
    assert result["test"]["status"] == "unavailable"


def test_sparse_table_warns_about_expected_counts():
    df = table_df({
        ("a", "x"): 5, ("a", "y"): 1, ("b", "x"): 1, ("b", "z"): 1, ("c", "y"): 2,
    })

    result = compare_categorical(df, "group", "outcome")

    assert result["test"]["status"] == "ok"
    assert any("below 1" in w for w in result["warnings"])
    assert any("below 5" in w for w in result["warnings"])
    # Combinations that never occur still appear as zero counts.
    assert 0 in np.array(result["counts"])


def test_too_many_categories_is_unavailable_with_reason():
    df = pd.DataFrame({"group": list("abcde"), "outcome": list("xyxyx")})

    result = compare_categorical(df, "group", "outcome", max_categories=4)

    assert result["status"] == "unavailable"
    assert "5 categories" in result["reason"]
    assert "at most 4" in result["reason"]


def test_boolean_columns_keep_their_labels():
    df = pd.DataFrame({"flag": [True, False, True, True], "outcome": list("xyxy")})

    result = compare_categorical(df, "flag", "outcome")

    assert result["group_categories"] == [True, False]
    assert result["counts"] == [[2, 1], [0, 1]]


@pytest.mark.parametrize(
    ("group", "outcome", "message"),
    [
        ("missing", "outcome", "does not exist"),
        ("group", "number", "is numeric"),
        ("group", "group", "two different columns"),
    ],
)
def test_invalid_selections_raise(group, outcome, message):
    df = pd.DataFrame({"group": ["a", "b"], "outcome": ["x", "y"], "number": [1, 2]})

    with pytest.raises(ComparisonError, match=message):
        compare_categorical(df, group, outcome)
