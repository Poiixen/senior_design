"""Compare a numeric measurement across the groups of a categorical column.

Only independent groups are supported: each row is one observation and no
subject appears in more than one group. The caller picks a method:

* ``auto`` (the default, unchanged since Ticket #51): Welch's t-test for two
  groups, Kruskal-Wallis for three or more.
* ``welch_t_test``: compares the means of exactly two groups.
* ``welch_anova``: compares the means of three or more groups with Welch's
  (1951) heteroscedastic one-way ANOVA, which does not assume equal variances.
* ``kruskal_wallis``: compares ranks across two or more groups.

Paired tests, two-way ANOVA and post-hoc pairwise comparisons are out of scope.
"""

import warnings as py_warnings

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype
from scipy.stats import f as f_distribution
from scipy.stats import kruskal, ttest_ind

from backend.diagnostics.comparison_common import (
    DESIGN_NOTE,
    MAX_COMPARISON_CATEGORIES,
    ComparisonError,
    json_label,
    ordered_counts,
    require_categorical,
    require_column,
    row_counts,
)

# Results without this field were saved before Ticket #57 (version 1).
RESULT_VERSION = 2
CONFIDENCE_LEVEL = 0.95
WHISKER_MULTIPLIER = 1.5

# Below these group sizes a warning explains the method's reduced reliability.
WELCH_SMALL_GROUP = 30
KRUSKAL_SMALL_GROUP = 5

NOT_PROOF_OF_EQUALITY = (
    "A p-value above the chosen significance level does not show the groups "
    "are equal; it means this data did not provide clear evidence of a difference."
)

WELCH = {
    "key": "welch_t_test",
    "name": "Welch's independent-samples t-test",
    "evaluates": "Whether the mean of the measurement differs between the two groups.",
    "null_hypothesis": "The two groups have equal population means.",
    "assumptions": [
        DESIGN_NOTE,
        "Each group's mean is approximately normally distributed: the values "
        "are roughly normal, or the group is large enough for the central "
        "limit theorem to apply. Strong skew or outliers in small groups make "
        "the p-value unreliable.",
        "The groups do not need equal variances.",
    ],
    "limitations": [
        "Compares exactly two groups.",
        NOT_PROOF_OF_EQUALITY,
        "The confidence interval for the mean difference relies on the same "
        "assumptions as the test.",
    ],
}

WELCH_ANOVA = {
    "key": "welch_anova",
    "name": "Welch's one-way ANOVA",
    "evaluates": (
        "Whether the mean of the measurement differs across three or more "
        "groups, without assuming the groups have equal variances."
    ),
    "null_hypothesis": "All groups have equal population means.",
    "variant": "welch",
    "assumptions": [
        DESIGN_NOTE,
        "Each group's mean is approximately normally distributed: the values "
        "are roughly normal, or the group is large enough for the central "
        "limit theorem to apply. Strong skew or outliers in small groups make "
        "the p-value unreliable.",
        "Group variances may differ. This is Welch's (1951) ANOVA, not the "
        "classical F-test, which assumes equal variances.",
        "Each group needs at least two values with some variation, because "
        "groups are weighted by their size divided by their variance.",
    ],
    "limitations": [
        "The overall test says whether at least one group mean differs; it "
        "does not identify which groups differ. Pairwise (post-hoc) "
        "comparisons are not provided.",
        NOT_PROOF_OF_EQUALITY,
        "Eta squared describes the share of variation between group means in "
        "this sample; it does not adjust for unequal variances.",
    ],
}

KRUSKAL_WALLIS = {
    "key": "kruskal_wallis",
    "name": "Kruskal-Wallis H test",
    "evaluates": (
        "Whether values tend to be higher in some groups than in others, using "
        "the ranks of the values rather than the values themselves. It is not "
        "a test of means."
    ),
    "null_hypothesis": "All groups come from the same distribution.",
    "assumptions": [
        DESIGN_NOTE,
        "Values can be meaningfully ranked.",
        "It can be read as a comparison of medians only when every group's "
        "distribution has the same shape and spread.",
        "A significant result means at least one group differs; it does not "
        "say which. Pairwise follow-up tests are not provided.",
    ],
    "limitations": [
        "Rank-based: it does not compare means.",
        NOT_PROOF_OF_EQUALITY,
    ],
}

METHODS = {method["key"]: method for method in (WELCH, WELCH_ANOVA, KRUSKAL_WALLIS)}
METHOD_CHOICES = ("auto", *METHODS)

AUTO_RULE = (
    "auto uses Welch's t-test for two groups and Kruskal-Wallis for three or "
    "more. Request welch_anova to compare means across three or more groups."
)

BOX_PLOT = {
    "quartile_method": "linear interpolation (pandas/numpy default)",
    "whisker_rule": (
        f"Tukey: whiskers reach the most extreme values within "
        f"{WHISKER_MULTIPLIER} x IQR of the quartiles."
    ),
    "outliers": "Values beyond the whiskers are counted in outlier_count.",
}


def _number(value):
    value = float(value)
    return value if np.isfinite(value) else None


def _summary(values: pd.Series) -> dict:
    """Quartiles use linear interpolation, matching the column profiles.

    Whiskers follow Tukey's rule, so a box plot drawn from these fields
    agrees with the quartiles used everywhere else.
    """
    q1, q3 = values.quantile(0.25), values.quantile(0.75)
    spread = WHISKER_MULTIPLIER * (q3 - q1)
    inside = (values >= q1 - spread) & (values <= q3 + spread)
    return {
        "count": int(len(values)),
        "mean": _number(values.mean()),
        "median": _number(values.median()),
        "std_dev": _number(values.std()) if len(values) > 1 else None,
        "min": _number(values.min()),
        "q1": _number(q1),
        "q3": _number(q3),
        "max": _number(values.max()),
        "whisker_low": _number(values[inside].min()),
        "whisker_high": _number(values[inside].max()),
        "outlier_count": int((~inside).sum()),
    }


def _unavailable(method: dict, reason: str, group_sizes: list) -> dict:
    return {
        "method": method,
        "status": "unavailable",
        "reason": reason,
        "group_sizes": group_sizes,
    }


def _quoted(labels) -> str:
    return ", ".join(repr(str(label)) for label in labels)


def _too_small(labels: list, arrays: list[np.ndarray], minimum: int) -> list:
    return [label for label, values in zip(labels, arrays) if len(values) < minimum]


def _normality_warning(labels: list, arrays: list[np.ndarray], method_name: str) -> list:
    small = _too_small(labels, arrays, WELCH_SMALL_GROUP)
    if not small:
        return []
    return [
        f"Group(s) {_quoted(small)} have fewer than {WELCH_SMALL_GROUP} values. "
        f"{method_name} assumes approximately normal group means, so check "
        "those groups for skew or outliers."
    ]


def _welch(labels: list, arrays: list[np.ndarray], group_sizes: list) -> tuple[dict, list]:
    small = _too_small(labels, arrays, 2)
    if small:
        return _unavailable(
            WELCH,
            "Welch's t-test needs at least two values in each group; "
            f"{_quoted(small)} has fewer.",
            group_sizes,
        ), []
    if all(np.ptp(values) == 0 for values in arrays):
        return _unavailable(
            WELCH,
            "Both groups contain a single repeated value, so their variability "
            "is zero and the t statistic is undefined.",
            group_sizes,
        ), []

    first, second = arrays
    result = ttest_ind(first, second, equal_var=False)
    interval = result.confidence_interval(CONFIDENCE_LEVEL)
    standard_error = np.sqrt(
        first.var(ddof=1) / len(first) + second.var(ddof=1) / len(second)
    )
    return {
        "method": WELCH,
        "status": "ok",
        "reason": None,
        "statistic_name": "t",
        "statistic": _number(result.statistic),
        "degrees_of_freedom": _number(result.df),
        "p_value": _number(result.pvalue),
        "group_sizes": group_sizes,
        "mean_difference": _number(first.mean() - second.mean()),
        "difference_order": [json_label(labels[0]), json_label(labels[1])],
        "mean_difference_ci": {
            "level": CONFIDENCE_LEVEL,
            "lower": _number(interval.low),
            "upper": _number(interval.high),
            "standard_error": _number(standard_error),
            "degrees_of_freedom": _number(result.df),
            "calculation": (
                "Welch-Satterthwaite interval: (mean of first group - mean of "
                "second group) +/- t(0.975, df) x sqrt(s1^2/n1 + s2^2/n2), "
                "using the test's degrees of freedom."
            ),
        },
    }, _normality_warning(labels, arrays, "Welch's t-test")


def welch_anova(arrays: list[np.ndarray]) -> dict:
    """Welch's (1951) F statistic, its degrees of freedom and p-value.

    Each group needs at least two values and a non-zero variance. With
    weights w_i = n_i / s_i^2 and weighted grand mean m_w:

        A   = sum(w_i * (m_i - m_w)^2) / (k - 1)
        lam = sum((1 - w_i / sum(w))^2 / (n_i - 1))
        F   = A / (1 + 2 * (k - 2) * lam / (k^2 - 1))
        df  = (k - 1, (k^2 - 1) / (3 * lam))
    """
    k = len(arrays)
    n = np.array([len(values) for values in arrays], dtype=float)
    means = np.array([values.mean() for values in arrays])
    weights = n / np.array([values.var(ddof=1) for values in arrays])
    total_weight = weights.sum()
    weighted_mean = (weights * means).sum() / total_weight
    between = (weights * (means - weighted_mean) ** 2).sum() / (k - 1)
    lam = ((1 - weights / total_weight) ** 2 / (n - 1)).sum()
    statistic = between / (1 + 2 * (k - 2) * lam / (k**2 - 1))
    df_between, df_within = k - 1, (k**2 - 1) / (3 * lam)
    return {
        "statistic": statistic,
        "df_between": df_between,
        "df_within": df_within,
        "p_value": f_distribution.sf(statistic, df_between, df_within),
    }


def _eta_squared(arrays: list[np.ndarray]) -> float:
    combined = np.concatenate(arrays)
    grand_mean = combined.mean()
    between = sum(len(values) * (values.mean() - grand_mean) ** 2 for values in arrays)
    return between / ((combined - grand_mean) ** 2).sum()


def _welch_anova(labels: list, arrays: list[np.ndarray], group_sizes: list) -> tuple[dict, list]:
    small = _too_small(labels, arrays, 2)
    if small:
        return _unavailable(
            WELCH_ANOVA,
            "Welch's ANOVA needs at least two values in each group; "
            f"{_quoted(small)} has fewer. Combine small categories or choose "
            "another column.",
            group_sizes,
        ), []
    constant = [label for label, values in zip(labels, arrays) if np.ptp(values) == 0]
    if constant:
        return _unavailable(
            WELCH_ANOVA,
            f"Group(s) {_quoted(constant)} contain a single repeated value. "
            "Welch's ANOVA weights each group by its size divided by its "
            "variance, so a group with zero variance makes the test undefined. "
            "Kruskal-Wallis can still compare ranks.",
            group_sizes,
        ), []

    result = welch_anova(arrays)
    return {
        "method": WELCH_ANOVA,
        "status": "ok",
        "reason": None,
        "statistic_name": "F",
        "statistic": _number(result["statistic"]),
        # Numerator df, as for the other tests; the denominator is separate.
        "degrees_of_freedom": result["df_between"],
        "degrees_of_freedom_between": result["df_between"],
        "degrees_of_freedom_within": _number(result["df_within"]),
        "p_value": _number(result["p_value"]),
        "group_sizes": group_sizes,
        "eta_squared": _number(_eta_squared(arrays)),
        "eta_squared_calculation": (
            "Sum of squares between group means divided by the total sum of "
            "squares around the overall mean (descriptive)."
        ),
    }, _normality_warning(labels, arrays, "Welch's ANOVA")


def _kruskal(labels: list, arrays: list[np.ndarray], group_sizes: list) -> tuple[dict, list]:
    combined = np.concatenate(arrays)
    if np.ptp(combined) == 0:
        return _unavailable(
            KRUSKAL_WALLIS,
            "Every included value is identical, so there is no variation to rank.",
            group_sizes,
        ), []
    if len(combined) <= len(arrays):
        return _unavailable(
            KRUSKAL_WALLIS,
            "Every group has a single value; the test needs more observations "
            "than groups.",
            group_sizes,
        ), []

    result = kruskal(*arrays)
    warnings = []
    small = _too_small(labels, arrays, KRUSKAL_SMALL_GROUP)
    if small:
        warnings.append(
            f"Group(s) {_quoted(small)} have fewer than "
            f"{KRUSKAL_SMALL_GROUP} values. The p-value uses a chi-square "
            "approximation that can be inaccurate for groups this small."
        )
    return {
        "method": KRUSKAL_WALLIS,
        "status": "ok",
        "reason": None,
        "statistic_name": "H",
        "statistic": _number(result.statistic),
        "degrees_of_freedom": len(arrays) - 1,
        "p_value": _number(result.pvalue),
        "group_sizes": group_sizes,
    }, warnings


RUNNERS = {"welch_t_test": _welch, "welch_anova": _welch_anova, "kruskal_wallis": _kruskal}


def _select_method(requested: str, group_count: int) -> dict:
    if requested == "auto":
        return WELCH if group_count == 2 else KRUSKAL_WALLIS
    return METHODS[requested]


def _group_count_problem(method: dict, group_count: int) -> str | None:
    """Why ``method`` cannot compare this many groups, or None if it can."""
    if method is WELCH and group_count > 2:
        return (
            f"Welch's t-test compares exactly two groups; this selection has "
            f"{group_count}. Request welch_anova to compare means or "
            "kruskal_wallis to compare ranks, or combine categories."
        )
    if method is WELCH_ANOVA and group_count == 2:
        return (
            "Welch's ANOVA is offered for three or more groups; this selection "
            "has two. Request welch_t_test, which runs the equivalent test and "
            "also returns the mean difference and its confidence interval."
        )
    return None


def _analysis_question(method: dict, group_column: str, value_column: str) -> dict:
    if method is KRUSKAL_WALLIS:
        return {
            "key": "compare_ranks",
            "text": f"Do values of '{value_column}' tend to be higher in some "
            f"'{group_column}' groups than in others?",
        }
    groups = "the two" if method is WELCH else "the"
    return {
        "key": "compare_means",
        "text": f"Does the mean of '{value_column}' differ across {groups} "
        f"'{group_column}' groups?",
    }


def compare_numeric_across_groups(
    df: pd.DataFrame,
    group_column: str,
    value_column: str,
    max_groups: int = MAX_COMPARISON_CATEGORIES,
    method: str = "auto",
) -> dict:
    """Summarise ``value_column`` within each group of ``group_column``.

    Rows with a missing group label or a missing or non-finite measurement
    are excluded and counted by reason (a row can match both). Groups are
    ordered by descending size, then label. ``method`` is one of
    ``METHOD_CHOICES``; see the module docstring. For Welch's t-test
    ``mean_difference`` is the first listed group minus the second.

    Raises ComparisonError for selections that can never be compared.
    Data that cannot be compared (no usable rows, too many groups) returns
    ``status`` "unavailable" with a ``reason``; summaries whose test cannot
    run, including a method that does not fit the number of groups, return
    an unavailable ``test``.
    """
    if method not in METHOD_CHOICES:
        raise ComparisonError(
            f"Unknown method '{method}'. Choose one of: {', '.join(METHOD_CHOICES)}."
        )
    groups = require_categorical(df, group_column)
    measurements = require_column(df, value_column)
    if is_bool_dtype(measurements) or not is_numeric_dtype(measurements):
        raise ComparisonError(
            f"Column '{value_column}' is not numeric ({measurements.dtype}), so "
            "it cannot be used as the measurement."
        )
    if group_column == value_column:
        raise ComparisonError("Choose two different columns to compare.")

    # Nullable integer columns hold pd.NA, which a plain float cast rejects.
    values = pd.Series(
        measurements.to_numpy(dtype="float64", na_value=np.nan),
        index=measurements.index,
    )
    missing_group = groups.isna()
    unusable_value = ~np.isfinite(values)
    included = ~missing_group & ~unusable_value
    groups, values = groups[included], values[included]
    labels = list(ordered_counts(groups).index)
    selected = _select_method(method, len(labels))

    result = {
        "comparison_type": "categorical_numeric",
        "design": "independent_groups",
        "selection": {"group_column": group_column, "value_column": value_column},
        "status": "ok",
        "reason": None,
        "rows": row_counts(
            len(df),
            int(included.sum()),
            missing_group_value=int(missing_group.sum()),
            missing_or_non_finite_value=int(unusable_value.sum()),
        ),
        "overall": None,
        "groups": [],
        "test": None,
        "warnings": [],
        "note": DESIGN_NOTE,
        "result_version": RESULT_VERSION,
        "analysis_question": _analysis_question(selected, group_column, value_column),
        "method_selection": {
            "requested": method,
            "selected": selected["key"],
            "rule": AUTO_RULE if method == "auto" else "Chosen by the request.",
        },
        "box_plot": BOX_PLOT,
    }

    def unavailable(reason: str) -> dict:
        result.update(
            status="unavailable", reason=reason, test=_unavailable(selected, reason, [])
        )
        return result

    if not included.any():
        return unavailable(
            "No rows have both a group label and a finite measurement."
        )
    if len(labels) > max_groups:
        return unavailable(
            f"Column '{group_column}' has {len(labels)} groups in the compared "
            f"rows; comparisons support at most {max_groups}. Choose a column "
            "with fewer categories or combine rare categories first."
        )

    arrays = [values[groups == label].to_numpy() for label in labels]
    group_sizes = [
        {"label": json_label(label), "count": len(array)}
        for label, array in zip(labels, arrays)
    ]
    result["overall"] = _summary(values)
    result["groups"] = [
        {"label": json_label(label), **_summary(values[groups == label])}
        for label in labels
    ]

    if len(labels) < 2:
        result["test"] = _unavailable(
            selected,
            f"Column '{group_column}' has only one group in the compared rows; "
            "at least two are needed.",
            group_sizes,
        )
        return result
    problem = _group_count_problem(selected, len(labels))
    if problem:
        result["test"] = _unavailable(selected, problem, group_sizes)
        return result

    with py_warnings.catch_warnings():
        py_warnings.simplefilter("ignore", RuntimeWarning)
        result["test"], result["warnings"] = RUNNERS[selected["key"]](
            labels, arrays, group_sizes
        )
    return result
