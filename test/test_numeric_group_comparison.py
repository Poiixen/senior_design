"""Numeric measurements compared across categorical groups."""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import kruskal, ttest_ind

from backend.diagnostics.comparison_common import ComparisonError
from backend.diagnostics.numeric_group_comparison import compare_numeric_across_groups


TWO_GROUPS = pd.DataFrame({
    "income": ["<=50K"] * 6 + [">50K"] * 4,
    "age": [22, 25, 31, 28, 40, 19, 45, 52, 38, 60],
})

THREE_GROUPS = pd.DataFrame({
    "education": ["HS"] * 5 + ["BA"] * 4 + ["MA"] * 3,
    "hours": [40, 35, 45, 50, 38, 42, 55, 48, 60, 50, 65, 58],
})


def by_label(result):
    return {group["label"]: group for group in result["groups"]}


def test_group_summaries_match_direct_calculations():
    result = compare_numeric_across_groups(TWO_GROUPS, "income", "age")
    low = np.array([22, 25, 31, 28, 40, 19], dtype=float)

    summary = by_label(result)["<=50K"]
    assert summary["count"] == 6
    assert summary["mean"] == pytest.approx(low.mean())
    assert summary["median"] == pytest.approx(np.median(low))
    assert summary["std_dev"] == pytest.approx(low.std(ddof=1))
    assert summary["q1"] == pytest.approx(np.quantile(low, 0.25))
    assert summary["q3"] == pytest.approx(np.quantile(low, 0.75))
    assert (summary["min"], summary["max"]) == (19.0, 40.0)
    assert result["overall"]["count"] == 10
    assert [g["label"] for g in result["groups"]] == ["<=50K", ">50K"]


def test_two_unequal_groups_use_welch_matching_scipy():
    result = compare_numeric_across_groups(TWO_GROUPS, "income", "age")
    low = [22, 25, 31, 28, 40, 19]
    high = [45, 52, 38, 60]
    expected = ttest_ind(low, high, equal_var=False)

    test = result["test"]
    assert test["status"] == "ok"
    assert test["method"]["key"] == "welch_t_test"
    assert test["statistic_name"] == "t"
    assert test["statistic"] == pytest.approx(expected.statistic)
    assert test["p_value"] == pytest.approx(expected.pvalue)
    assert test["degrees_of_freedom"] == pytest.approx(expected.df)
    assert test["group_sizes"] == [
        {"label": "<=50K", "count": 6},
        {"label": ">50K", "count": 4},
    ]
    assert test["mean_difference"] == pytest.approx(np.mean(low) - np.mean(high))
    assert test["difference_order"] == ["<=50K", ">50K"]
    assert any("fewer than 30" in w for w in result["warnings"])


def test_three_groups_use_kruskal_wallis_matching_scipy():
    result = compare_numeric_across_groups(THREE_GROUPS, "education", "hours")
    expected = kruskal(
        [40, 35, 45, 50, 38], [42, 55, 48, 60], [50, 65, 58]
    )

    test = result["test"]
    assert test["status"] == "ok"
    assert test["method"]["key"] == "kruskal_wallis"
    assert test["statistic_name"] == "H"
    assert test["statistic"] == pytest.approx(expected.statistic)
    assert test["p_value"] == pytest.approx(expected.pvalue)
    assert test["degrees_of_freedom"] == 2
    assert [g["count"] for g in test["group_sizes"]] == [5, 4, 3]
    assert "not a test of means" in test["method"]["evaluates"]
    assert any("fewer than 5" in w for w in result["warnings"])


def test_missing_and_non_finite_values_are_excluded_and_counted():
    df = pd.DataFrame({
        "group": ["a", "a", "a", "b", "b", "b", None, "b"],
        "value": [1.0, 2.0, np.nan, 3.0, np.inf, 4.0, 5.0, 6.0],
    })

    result = compare_numeric_across_groups(df, "group", "value")

    assert result["rows"] == {
        "total": 8,
        "included": 5,
        "excluded": 3,
        "exclusion_reasons": {
            "missing_group_value": 1,
            "missing_or_non_finite_value": 2,
        },
    }
    assert by_label(result)["b"]["count"] == 3
    assert result["test"]["statistic"] == pytest.approx(
        ttest_ind([3.0, 4.0, 6.0], [1.0, 2.0], equal_var=False).statistic
    )


def test_nullable_integer_measurements_are_supported():
    df = pd.DataFrame({
        "group": ["a", "a", "b", "b", "b"],
        "value": pd.array([1, None, 3, 4, 5], dtype="Int64"),
    })

    result = compare_numeric_across_groups(df, "group", "value")

    assert result["rows"]["included"] == 4
    assert result["test"]["status"] == "unavailable"  # group 'a' has one value


def test_unused_categories_of_a_category_column_are_ignored():
    df = pd.DataFrame({
        "group": pd.Categorical(["a", "a", "b", "b"], categories=["a", "b", "c"]),
        "value": [1.0, 2.0, 3.0, 5.0],
    })

    result = compare_numeric_across_groups(df, "group", "value")

    assert [g["label"] for g in result["groups"]] == ["a", "b"]
    assert result["test"]["method"]["key"] == "welch_t_test"


def test_one_constant_group_still_runs_welch():
    df = pd.DataFrame({"group": ["a"] * 3 + ["b"] * 3, "value": [5, 5, 5, 1, 2, 3]})

    result = compare_numeric_across_groups(df, "group", "value")

    assert by_label(result)["a"]["std_dev"] == 0.0
    assert result["test"]["status"] == "ok"
    assert result["test"]["statistic"] == pytest.approx(
        ttest_ind([5, 5, 5], [1, 2, 3], equal_var=False).statistic
    )


def test_two_constant_groups_make_welch_unavailable():
    df = pd.DataFrame({"group": ["a"] * 3 + ["b"] * 3, "value": [5, 5, 5, 7, 7, 7]})

    result = compare_numeric_across_groups(df, "group", "value")

    assert result["status"] == "ok"
    assert result["test"]["status"] == "unavailable"
    assert "variability is zero" in result["test"]["reason"]
    assert result["test"]["group_sizes"] == [
        {"label": "a", "count": 3},
        {"label": "b", "count": 3},
    ]


def test_identical_values_make_kruskal_wallis_unavailable():
    df = pd.DataFrame({"group": list("aabbcc"), "value": [3] * 6})

    result = compare_numeric_across_groups(df, "group", "value")

    assert result["test"]["method"]["key"] == "kruskal_wallis"
    assert result["test"]["status"] == "unavailable"
    assert "identical" in result["test"]["reason"]


def test_single_value_group_makes_welch_unavailable():
    df = pd.DataFrame({"group": ["a", "b", "b"], "value": [1, 2, 3]})

    result = compare_numeric_across_groups(df, "group", "value")

    assert result["test"]["status"] == "unavailable"
    assert "at least two values in each group" in result["test"]["reason"]
    assert by_label(result)["a"]["std_dev"] is None


def test_single_value_per_group_makes_kruskal_wallis_unavailable():
    df = pd.DataFrame({"group": list("abc"), "value": [1, 2, 3]})

    result = compare_numeric_across_groups(df, "group", "value")

    assert result["test"]["status"] == "unavailable"
    assert "single value" in result["test"]["reason"]


def test_one_group_gives_summary_but_no_test():
    df = pd.DataFrame({"group": ["a", "a", None], "value": [1, 2, 3]})

    result = compare_numeric_across_groups(df, "group", "value")

    assert [g["label"] for g in result["groups"]] == ["a"]
    assert result["test"]["status"] == "unavailable"
    assert "only one group" in result["test"]["reason"]


def test_no_usable_rows_is_unavailable():
    df = pd.DataFrame({"group": ["a", None], "value": [np.nan, 1.0]})

    result = compare_numeric_across_groups(df, "group", "value")

    assert result["status"] == "unavailable"
    assert result["groups"] == []
    assert result["rows"]["included"] == 0


def test_too_many_groups_is_unavailable_with_reason():
    df = pd.DataFrame({"group": list("abcd") * 2, "value": range(8)})

    result = compare_numeric_across_groups(df, "group", "value", max_groups=3)

    assert result["status"] == "unavailable"
    assert "4 groups" in result["reason"]


def test_result_describes_an_independent_group_design():
    result = compare_numeric_across_groups(TWO_GROUPS, "income", "age")

    assert result["comparison_type"] == "categorical_numeric"
    assert result["design"] == "independent_groups"
    assert "Paired or repeated" in result["note"]
    assert result["selection"] == {"group_column": "income", "value_column": "age"}


@pytest.mark.parametrize(
    ("group", "value", "message"),
    [
        ("missing", "value", "does not exist"),
        ("group", "missing", "does not exist"),
        ("number", "value", "is numeric"),
        ("group", "label", "not numeric"),
        ("group", "flag", "not numeric"),
    ],
)
def test_invalid_selections_raise(group, value, message):
    df = pd.DataFrame({
        "group": ["a", "b"],
        "label": ["x", "y"],
        "number": [1, 2],
        "value": [1.5, 2.5],
        "flag": [True, False],
    })

    with pytest.raises(ComparisonError, match=message):
        compare_numeric_across_groups(df, group, value)
