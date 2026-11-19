"""A short first reading must preserve the statistical interpretation."""
from backend.services.suggestions.plain_language import summarize
from test_suggestions_rules import example, only, findings


def test_plain_comparison_uses_adjusted_decision_without_jargon():
    first = example("categorical_numeric_two_groups_welch")
    second = example("categorical_numeric_three_plus_groups_kruskal_wallis")
    for index, comparison in enumerate((first, second), 1):
        comparison["comparison_id"] = index
        comparison["test"]["p_value"] = .03
    for candidate, _ in findings(comparisons=[first, second]):
        result = summarize(candidate)
        assert "did not detect a clear difference" in result["plain_summary"]
        assert "does not mean the groups are identical" in result["plain_summary"]
        assert "exploratory" in result["plain_caution"]
        assert len(result["plain_summary"].split()) < 45
        assert "p-value" not in result["plain_summary"]


def test_unreliable_expected_counts_remain_visible_in_short_view():
    result = summarize(only(comparisons=[example("categorical_categorical_warning")]))
    assert "too small for a reliable test" in result["plain_caution"]


def test_zero_iqr_summary_does_not_label_flagged_values_mistakes():
    candidate = only({"dataset": {"rows": 100}, "outliers": [{
        "column_name": "capital-gain", "outlier_count": 10, "outlier_percentage": 10,
        "q1": 0, "q3": 0, "iqr": 0, "lower_bound": 0, "upper_bound": 0,
    }]}, kind="outliers")
    result = summarize(candidate)
    assert "not necessarily mistakes" in result["plain_summary"]
    assert "flags every different value" in result["plain_caution"]
    assert "original records" in result["recommended_action"]
