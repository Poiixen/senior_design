"""Numeric measurements compared across categorical groups."""

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from scipy.stats import kruskal, ttest_ind

from backend.diagnostics.comparison_common import ComparisonError
from backend.diagnostics.numeric_group_comparison import (
    compare_numeric_across_groups,
    welch_anova,
)


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


# --- Ticket #57: method choice, Welch's ANOVA, confidence interval, box plots ---

UNEQUAL = pd.DataFrame({
    "group": ["a"] * 8 + ["b"] * 15 + ["c"] * 6 + ["d"] * 11,
    "value": np.concatenate([
        np.random.RandomState(7).normal(10, 1, 8),
        np.random.RandomState(8).normal(12, 3, 15),
        np.random.RandomState(9).normal(14, 6, 6),
        np.random.RandomState(10).normal(10, 2, 11),
    ]),
})


def arrays_by_group(df, labels):
    return [df.loc[df["group"] == label, "value"].to_numpy(dtype=float) for label in labels]


def textbook_welch_anova(arrays):
    """Welch (1951), written out independently of the implementation."""
    k = len(arrays)
    n = np.array([len(a) for a in arrays], dtype=float)
    m = np.array([np.mean(a) for a in arrays])
    w = n / np.array([np.var(a, ddof=1) for a in arrays])
    mw = np.sum(w * m) / np.sum(w)
    tmp = np.sum((1 - w / np.sum(w)) ** 2 / (n - 1)) / (k**2 - 1)
    f = (np.sum(w * (m - mw) ** 2) / (k - 1)) / (1 + 2 * (k - 2) * tmp)
    df2 = 1 / (3 * tmp)
    return f, k - 1, df2, stats.f.sf(f, k - 1, df2)


def test_auto_keeps_the_original_methods():
    two = compare_numeric_across_groups(TWO_GROUPS, "income", "age")
    three = compare_numeric_across_groups(THREE_GROUPS, "education", "hours")

    assert two["test"]["method"]["key"] == "welch_t_test"
    assert three["test"]["method"]["key"] == "kruskal_wallis"
    assert three["method_selection"]["requested"] == "auto"
    assert three["method_selection"]["selected"] == "kruskal_wallis"
    assert three["analysis_question"]["key"] == "compare_ranks"
    assert two["analysis_question"]["key"] == "compare_means"


def test_welch_anova_matches_textbook_formula_and_scipy():
    result = compare_numeric_across_groups(UNEQUAL, "group", "value", method="welch_anova")
    arrays = arrays_by_group(UNEQUAL, [g["label"] for g in result["groups"]])
    f, df1, df2, p = textbook_welch_anova(arrays)

    test = result["test"]
    assert test["status"] == "ok"
    assert test["method"]["key"] == "welch_anova"
    assert test["method"]["variant"] == "welch"
    assert test["statistic_name"] == "F"
    assert test["statistic"] == pytest.approx(f)
    assert test["degrees_of_freedom"] == df1 == test["degrees_of_freedom_between"]
    assert test["degrees_of_freedom_within"] == pytest.approx(df2)
    assert test["p_value"] == pytest.approx(p)
    assert result["analysis_question"]["key"] == "compare_means"
    assert result["method_selection"] == {
        "requested": "welch_anova",
        "selected": "welch_anova",
        "rule": "Chosen by the request.",
    }
    try:  # scipy >= 1.16 implements Welch's ANOVA directly
        expected = stats.f_oneway(*arrays, equal_var=False)
    except TypeError:
        return
    assert test["statistic"] == pytest.approx(expected.statistic)
    assert test["p_value"] == pytest.approx(expected.pvalue)


def test_welch_anova_eta_squared_matches_sums_of_squares():
    test = compare_numeric_across_groups(UNEQUAL, "group", "value", method="welch_anova")["test"]
    values = UNEQUAL["value"]
    grand = values.mean()
    between = UNEQUAL.groupby("group")["value"].apply(
        lambda g: len(g) * (g.mean() - grand) ** 2
    ).sum()

    assert test["eta_squared"] == pytest.approx(between / ((values - grand) ** 2).sum())


def test_welch_anova_with_two_groups_equals_welch_t_squared():
    first = np.array([1.0, 2, 4, 7, 9])
    second = np.array([3.0, 8, 9, 12, 15, 20, 21])

    result = welch_anova([first, second])

    t = ttest_ind(first, second, equal_var=False)
    assert result["statistic"] == pytest.approx(t.statistic**2)
    assert result["df_within"] == pytest.approx(t.df)
    assert result["p_value"] == pytest.approx(t.pvalue)


def test_welch_anova_states_what_it_cannot_say():
    method = compare_numeric_across_groups(
        UNEQUAL, "group", "value", method="welch_anova"
    )["test"]["method"]
    text = " ".join(method["limitations"] + method["assumptions"])

    assert "does not identify which groups differ" in text
    assert "does not show the groups are equal" in text
    assert "not the classical F-test" in text


def test_welch_anova_with_two_groups_points_to_welch_t_test():
    result = compare_numeric_across_groups(TWO_GROUPS, "income", "age", method="welch_anova")

    assert result["status"] == "ok"
    assert len(result["groups"]) == 2
    assert result["test"]["status"] == "unavailable"
    assert "welch_t_test" in result["test"]["reason"]


def test_welch_t_test_refuses_three_groups():
    result = compare_numeric_across_groups(
        THREE_GROUPS, "education", "hours", method="welch_t_test"
    )

    assert result["test"]["status"] == "unavailable"
    assert "exactly two groups" in result["test"]["reason"]


def test_kruskal_wallis_can_be_requested_for_two_groups():
    result = compare_numeric_across_groups(TWO_GROUPS, "income", "age", method="kruskal_wallis")

    expected = kruskal([22, 25, 31, 28, 40, 19], [45, 52, 38, 60])
    assert result["test"]["method"]["key"] == "kruskal_wallis"
    assert result["test"]["statistic"] == pytest.approx(expected.statistic)
    assert "does not compare means" in " ".join(result["test"]["method"]["limitations"])


@pytest.mark.parametrize(
    ("groups", "values", "needle"),
    [
        ("aaabbbc", [1, 2, 3, 4, 5, 6, 7], "at least two values"),
        ("aaabbcc", [1, 2, 3, 4, 5, 9, 9], "zero variance"),
    ],
)
def test_welch_anova_unavailable_cases(groups, values, needle):
    df = pd.DataFrame({"group": list(groups), "value": values})

    result = compare_numeric_across_groups(df, "group", "value", method="welch_anova")

    assert result["test"]["status"] == "unavailable"
    assert result["test"]["method"]["key"] == "welch_anova"
    assert needle in result["test"]["reason"]


def test_unknown_method_raises():
    with pytest.raises(ComparisonError, match="Unknown method"):
        compare_numeric_across_groups(TWO_GROUPS, "income", "age", method="anova")


def test_welch_confidence_interval_matches_scipy_and_formula():
    low = np.array([22, 25, 31, 28, 40, 19], dtype=float)
    high = np.array([45, 52, 38, 60], dtype=float)

    test = compare_numeric_across_groups(TWO_GROUPS, "income", "age")["test"]

    interval = test["mean_difference_ci"]
    expected = ttest_ind(low, high, equal_var=False).confidence_interval(0.95)
    se = np.sqrt(low.var(ddof=1) / 6 + high.var(ddof=1) / 4)
    margin = stats.t.ppf(0.975, test["degrees_of_freedom"]) * se
    assert interval["level"] == 0.95
    assert interval["lower"] == pytest.approx(expected.low)
    assert interval["upper"] == pytest.approx(expected.high)
    assert interval["lower"] == pytest.approx(test["mean_difference"] - margin)
    assert interval["standard_error"] == pytest.approx(se)


def test_unavailable_welch_has_no_interval():
    df = pd.DataFrame({"group": ["a"] * 3 + ["b"] * 3, "value": [5, 5, 5, 7, 7, 7]})

    test = compare_numeric_across_groups(df, "group", "value")["test"]

    assert "mean_difference_ci" not in test


def test_box_plot_whiskers_follow_tukey_rule():
    values = np.array([1, 2, 3, 4, 5, 6, 7, 8, 40], dtype=float)
    df = pd.DataFrame({"group": ["a"] * 9, "value": values})

    summary = compare_numeric_across_groups(df, "group", "value")["groups"][0]

    q1, q3 = np.quantile(values, [0.25, 0.75])
    fence = 1.5 * (q3 - q1)
    inside = values[(values >= q1 - fence) & (values <= q3 + fence)]
    assert (summary["q1"], summary["q3"]) == (q1, q3)
    assert summary["whisker_low"] == inside.min() == 1
    assert summary["whisker_high"] == inside.max() == 8
    assert summary["outlier_count"] == 1
    assert summary["max"] == 40


def test_chart_values_are_the_statistical_summaries():
    result = compare_numeric_across_groups(UNEQUAL, "group", "value", method="welch_anova")

    for group in result["groups"]:
        values = UNEQUAL.loc[UNEQUAL["group"] == group["label"], "value"]
        assert group["mean"] == pytest.approx(values.mean())
        assert group["min"] <= group["whisker_low"] <= group["q1"] <= group["median"]
        assert group["median"] <= group["q3"] <= group["whisker_high"] <= group["max"]
    assert [g["count"] for g in result["groups"]] == [
        g["count"] for g in result["test"]["group_sizes"]
    ]
    assert "Tukey" in result["box_plot"]["whisker_rule"]
    assert result["result_version"] == 2
