"""Compare a numeric measurement across the groups of a categorical column.

Only independent groups are supported: each row is one observation and no
subject appears in more than one group. The test is chosen by group count
alone: Welch's t-test for two groups, Kruskal-Wallis for three or more.
Paired tests and post-hoc pairwise comparisons are out of scope.
"""

import warnings as py_warnings

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype
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

# Below these group sizes a warning explains the method's reduced reliability.
WELCH_SMALL_GROUP = 30
KRUSKAL_SMALL_GROUP = 5

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
}


def _number(value):
    value = float(value)
    return value if np.isfinite(value) else None


def _summary(values: pd.Series) -> dict:
    """Quartiles use linear interpolation, matching the column profiles."""
    return {
        "count": int(len(values)),
        "mean": _number(values.mean()),
        "median": _number(values.median()),
        "std_dev": _number(values.std()) if len(values) > 1 else None,
        "min": _number(values.min()),
        "q1": _number(values.quantile(0.25)),
        "q3": _number(values.quantile(0.75)),
        "max": _number(values.max()),
    }


def _unavailable(method: dict, reason: str, group_sizes: list) -> dict:
    return {
        "method": method,
        "status": "unavailable",
        "reason": reason,
        "group_sizes": group_sizes,
    }


def _welch(labels: list, arrays: list[np.ndarray], group_sizes: list) -> tuple[dict, list]:
    small = [str(label) for label, values in zip(labels, arrays) if len(values) < 2]
    if small:
        return _unavailable(
            WELCH,
            "Welch's t-test needs at least two values in each group; "
            f"{', '.join(repr(s) for s in small)} has fewer.",
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
    warnings = []
    small = [
        str(label) for label, values in zip(labels, arrays)
        if len(values) < WELCH_SMALL_GROUP
    ]
    if small:
        warnings.append(
            f"Group(s) {', '.join(repr(s) for s in small)} have fewer than "
            f"{WELCH_SMALL_GROUP} values. Welch's t-test assumes approximately "
            "normal group means, so check those groups for skew or outliers."
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
    }, warnings


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
    small = [
        str(label) for label, values in zip(labels, arrays)
        if len(values) < KRUSKAL_SMALL_GROUP
    ]
    if small:
        warnings.append(
            f"Group(s) {', '.join(repr(s) for s in small)} have fewer than "
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


def compare_numeric_across_groups(
    df: pd.DataFrame,
    group_column: str,
    value_column: str,
    max_groups: int = MAX_COMPARISON_CATEGORIES,
) -> dict:
    """Summarise ``value_column`` within each group of ``group_column``.

    Rows with a missing group label or a missing or non-finite measurement
    are excluded and counted by reason (a row can match both). Groups are
    ordered by descending size, then label. Two groups are compared with
    Welch's t-test (``mean_difference`` is the first listed group minus the
    second); three or more with Kruskal-Wallis.

    Raises ComparisonError for selections that can never be compared.
    Data that cannot be compared (no usable rows, too many groups) returns
    ``status`` "unavailable" with a ``reason``; summaries whose test cannot
    run return an unavailable ``test``.
    """
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
    }

    groups, values = groups[included], values[included]
    labels = list(ordered_counts(groups).index)
    method = WELCH if len(labels) == 2 else KRUSKAL_WALLIS

    def unavailable(reason: str) -> dict:
        result.update(
            status="unavailable", reason=reason, test=_unavailable(method, reason, [])
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
            method,
            f"Column '{group_column}' has only one group in the compared rows; "
            "at least two are needed.",
            group_sizes,
        )
        return result

    with py_warnings.catch_warnings():
        py_warnings.simplefilter("ignore", RuntimeWarning)
        if len(labels) == 2:
            result["test"], result["warnings"] = _welch(labels, arrays, group_sizes)
        else:
            result["test"], result["warnings"] = _kruskal(labels, arrays, group_sizes)
    return result
