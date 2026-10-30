"""Statistical detail in suggestion wording: effect-size labels, degrees of
freedom, group summaries and Holm-adjusted p-values.

Comparison fixtures are the saved outputs in docs/examples/comparisons.
"""

import pytest

from backend.services.suggestions.fallback import (
    SIZE_CAVEAT,
    _cramers_v_cuts,
    _df,
    _size_label,
    COHENS_D_CUTS,
    ETA_SQUARED_CUTS,
    describe,
)
from backend.services.suggestions.rules import holm_adjust
from test_suggestions_rules import example, findings, only


# --- formatting and labels ---------------------------------------------------


@pytest.mark.parametrize(
    "value, label",
    [(0.0, "negligible"), (0.19, "negligible"), (0.2, "small"), (0.49, "small"),
     (0.5, "medium"), (0.79, "medium"), (0.8, "large"), (-1.4, "large")],
)
def test_cohens_d_label_boundaries(value, label):
    assert _size_label(value, COHENS_D_CUTS) == label


def test_eta_squared_uses_its_own_cutoffs():
    assert _size_label(0.005, ETA_SQUARED_CUTS) == "negligible"
    assert _size_label(0.06, ETA_SQUARED_CUTS) == "medium"
    assert _size_label(0.2, ETA_SQUARED_CUTS) == "large"


def test_degrees_of_freedom_keep_whole_numbers_whole():
    assert _df(4.0) == "4"
    assert _df(36.0262) == "36.03"
    assert _df(None) == "n/a"


def test_cramers_v_cutoffs_shrink_with_table_size():
    two_by_two = _cramers_v_cuts({"group_sizes": [1, 2], "degrees_of_freedom": 1})
    larger = _cramers_v_cuts({"group_sizes": [1, 2, 3, 4], "degrees_of_freedom": 9})
    assert two_by_two == pytest.approx((0.1, 0.3, 0.5))
    assert all(big < small for big, small in zip(larger, two_by_two))


def test_cramers_v_cutoffs_are_unknown_without_a_table_shape():
    assert _cramers_v_cuts({"group_sizes": [1], "degrees_of_freedom": 1}) is None
    assert _cramers_v_cuts({"group_sizes": [1, 2], "degrees_of_freedom": None}) is None


# --- wording of one comparison ------------------------------------------------


def test_welch_explanation_reports_df_effect_size_and_group_medians():
    parts = describe(only(comparisons=[example("categorical_numeric_two_groups_welch")]))
    text = " ".join([parts["explanation"], *parts["evidence"]])
    assert "degrees of freedom" in text
    assert "Cohen's d" in text
    assert "median" in text
    assert SIZE_CAVEAT in parts["explanation"]


def test_effect_size_label_describes_magnitude_not_importance():
    parts = describe(only(comparisons=[example("categorical_numeric_two_groups_welch")]))
    lowered = " ".join([parts["explanation"], *parts["evidence"]]).lower()
    assert "practically important" not in lowered
    assert "caused by" not in lowered


def test_a_single_comparison_has_no_adjusted_p_value():
    candidate = only(comparisons=[example("categorical_numeric_two_groups_welch")])
    assert "p_value_adjusted" not in candidate.values
    assert not candidate.exploratory


# --- Holm adjustment ------------------------------------------------------------


def test_holm_adjust_matches_the_textbook_example():
    # Sorted: 0.01*4, 0.02*3, 0.03*2, 0.04*1 -> 0.04, 0.06, 0.06, 0.06 (kept non-decreasing)
    assert holm_adjust([0.04, 0.01, 0.03, 0.02]) == pytest.approx([0.06, 0.04, 0.06, 0.06])


def test_holm_adjust_caps_at_one_and_keeps_missing_values():
    assert holm_adjust([0.9, None, 0.8]) == pytest.approx([1.0, None, 1.0])
    assert holm_adjust([]) == []


def test_several_tests_get_adjusted_p_values_and_an_exploratory_flag():
    first = example("categorical_numeric_two_groups_welch")
    second = example("categorical_numeric_three_plus_groups_kruskal_wallis")
    for index, comparison in enumerate((first, second), start=1):
        comparison["comparison_id"] = index
    candidates = [c for c, _ in findings(comparisons=[first, second])]
    assert len(candidates) == 2
    for candidate in candidates:
        assert candidate.exploratory
        assert candidate.values["p_adjustment"] == {"method": "holm", "comparisons": 2}
        assert candidate.values["p_value_adjusted"] >= candidate.values["p_value"]
        assert candidate.values["significant_at_0_05"] == (candidate.values["p_value_adjusted"] < 0.05)


def test_rerunning_a_comparison_does_not_inflate_the_adjustment():
    older = example("categorical_numeric_two_groups_welch")
    older["comparison_id"] = 3
    newer = example("categorical_numeric_two_groups_welch")
    newer["comparison_id"] = 8
    candidate = only(comparisons=[older, newer])
    assert "p_adjustment" not in candidate.values
    assert not candidate.exploratory
