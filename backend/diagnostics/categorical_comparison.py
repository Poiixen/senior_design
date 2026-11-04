"""Category frequency breakdowns and categorical-vs-categorical comparisons.

Results are descriptive: an association between two columns says how their
categories co-occur in this dataset, not why, and is not evidence of
causation or of bias.
"""

from math import sqrt
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

from backend.diagnostics.comparison_common import (
    DESIGN_NOTE,
    MAX_COMPARISON_CATEGORIES,
    MAX_CONTINGENCY_CELLS,
    WARN_CONTINGENCY_CELLS,
    ComparisonError,
    json_label,
    ordered_counts,
    require_categorical,
    row_counts,
)

# Column profiles list at most this many categories; the rest are summarised
# by ``omitted_categories`` and ``omitted_count``.
MAX_PROFILE_CATEGORIES = 500

ASSOCIATION_NOTE = (
    "These results describe how categories co-occur in this dataset. An "
    "association does not show that one column causes the other and is not, "
    "by itself, evidence of bias."
)

CHI_SQUARE = {
    "key": "chi_square_independence",
    "name": "Pearson's chi-square test of independence",
    "evaluates": (
        "Whether the distribution of the outcome column's categories differs "
        "between groups more than chance would explain."
    ),
    "null_hypothesis": "The two columns are independent.",
    "assumptions": [
        DESIGN_NOTE,
        "Expected counts are large enough for the chi-square approximation: "
        "none below 1 and no more than 20% below 5.",
    ],
}

CRAMERS_V = {
    "key": "cramers_v",
    "name": "Cramér's V",
    "evaluates": (
        "Strength of association from 0 (none) to 1 (one column determines "
        "the other). It does not indicate direction or cause."
    ),
}


def _percentage(count: int, denominator: int) -> Optional[float]:
    return round(count / denominator * 100, 2) if denominator else None


def category_distribution(column: pd.Series) -> dict:
    """Every category's count and share of the column's non-missing rows.

    Categories are ordered by descending count, then by label text. Columns
    with more than ``MAX_PROFILE_CATEGORIES`` categories list the largest
    ones and report how many categories and rows were left out.
    """
    total_rows = len(column)
    non_missing = int(column.count())
    counts = ordered_counts(column)
    listed = counts.iloc[:MAX_PROFILE_CATEGORIES]
    return {
        "distinct_categories": len(counts),
        "total_rows": total_rows,
        "non_missing_rows": non_missing,
        "missing_rows": total_rows - non_missing,
        "percentage_denominator": "non_missing_rows",
        "categories": [
            {
                "label": json_label(label),
                "count": int(count),
                "percentage": _percentage(int(count), non_missing),
            }
            for label, count in listed.items()
        ],
        "categories_truncated": len(counts) > len(listed),
        "omitted_categories": len(counts) - len(listed),
        "omitted_count": int(counts.iloc[len(listed):].sum()),
    }


def _unavailable(method: dict, reason: str) -> dict:
    return {"method": method, "status": "unavailable", "reason": reason}


def _expected_count_warnings(expected: np.ndarray) -> list[str]:
    warnings = []
    cells = expected.size
    below_five = int((expected < 5).sum())
    if (expected < 1).any():
        warnings.append(
            "At least one expected count is below 1, so the chi-square p-value "
            "may be unreliable. Consider combining rare categories."
        )
    if below_five / cells > 0.2:
        warnings.append(
            f"{below_five} of {cells} cells ({below_five / cells:.0%}) have "
            "expected counts below 5, so the chi-square p-value may be "
            "unreliable. Consider combining rare categories."
        )
    return warnings


def expected_count_summary(expected: np.ndarray) -> dict:
    """Counts behind the expected-frequency warnings, for before/after review."""
    cells = int(expected.size)
    below_five = int((expected < 5).sum())
    return {
        "cells": cells,
        "cells_below_5": below_five,
        "cells_below_1": int((expected < 1).sum()),
        "share_below_5": round(below_five / cells, 4),
        "guideline": "No expected count below 1 and at most 20% of cells below 5.",
        "meets_guideline": bool(not (expected < 1).any() and below_five / cells <= 0.2),
    }


def compare_categorical(
    df: pd.DataFrame,
    group_column: str,
    outcome_column: str,
    max_categories: int = MAX_COMPARISON_CATEGORIES,
    max_cells: int = MAX_CONTINGENCY_CELLS,
    warn_cells: int = WARN_CONTINGENCY_CELLS,
) -> dict:
    """Cross-tabulate two categorical columns and test their independence.

    Rows missing either value are excluded and counted. ``counts[i][j]`` is
    the number of rows in group ``group_categories[i]`` with outcome
    ``outcome_categories[j]``; ``row_percentages`` divides each count by its
    group's total. Categories keep their labels, ordered by descending count.

    Raises ComparisonError for selections that can never be compared
    (unknown, numeric or identical columns). Data that cannot be compared
    (no complete rows, too many categories) returns ``status`` "unavailable"
    with a ``reason``; a table whose test cannot run returns an unavailable
    ``test`` and ``association``.
    """
    groups = require_categorical(df, group_column)
    outcomes = require_categorical(df, outcome_column)
    if group_column == outcome_column:
        raise ComparisonError("Choose two different columns to compare.")

    missing_group = groups.isna()
    missing_outcome = outcomes.isna()
    included = ~missing_group & ~missing_outcome
    result = {
        "comparison_type": "categorical_categorical",
        "design": "independent_groups",
        "selection": {"group_column": group_column, "outcome_column": outcome_column},
        "status": "ok",
        "reason": None,
        "rows": row_counts(
            len(df),
            int(included.sum()),
            missing_group_value=int(missing_group.sum()),
            missing_outcome_value=int(missing_outcome.sum()),
        ),
        "group_categories": [],
        "outcome_categories": [],
        "counts": [],
        "group_totals": [],
        "outcome_totals": [],
        "row_percentages": [],
        "percentage_denominator": "group_total",
        "test": None,
        "association": None,
        "warnings": [],
        "note": ASSOCIATION_NOTE,
    }

    def unavailable(reason: str) -> dict:
        result.update(
            status="unavailable",
            reason=reason,
            test=_unavailable(CHI_SQUARE, reason),
            association=_unavailable(CRAMERS_V, reason),
        )
        return result

    if not included.any():
        return unavailable("No rows have values in both selected columns.")

    groups, outcomes = groups[included], outcomes[included]
    group_order = list(ordered_counts(groups).index)
    outcome_order = list(ordered_counts(outcomes).index)
    for name, order in ((group_column, group_order), (outcome_column, outcome_order)):
        if len(order) > max_categories:
            return unavailable(
                f"Column '{name}' has {len(order)} categories in the compared "
                f"rows; comparisons support at most {max_categories}. Choose a "
                "column with fewer categories or combine rare categories first."
            )

    cell_count = len(group_order) * len(outcome_order)
    if cell_count > max_cells:
        return unavailable(
            f"This comparison would create {cell_count:,} cells "
            f"({len(group_order)} × {len(outcome_order)} categories); comparisons "
            f"support at most {max_cells:,} cells. Choose columns with fewer "
            "categories or combine rare categories first."
        )
    if cell_count > warn_cells:
        result["warnings"].append(
            f"This is a large contingency table with {cell_count:,} cells "
            f"({len(group_order)} × {len(outcome_order)} categories). It may be "
            "difficult to read and sparse; review the expected-frequency warnings."
        )

    table = (
        pd.crosstab(groups, outcomes)
        .reindex(index=group_order, columns=outcome_order, fill_value=0)
        .to_numpy(dtype=np.int64)
    )
    group_totals = table.sum(axis=1)
    result.update(
        group_categories=[json_label(label) for label in group_order],
        outcome_categories=[json_label(label) for label in outcome_order],
        counts=table.tolist(),
        group_totals=group_totals.tolist(),
        outcome_totals=table.sum(axis=0).tolist(),
        row_percentages=[
            [_percentage(int(count), int(total)) for count in row]
            for row, total in zip(table, group_totals)
        ],
    )

    for name, order in ((group_column, group_order), (outcome_column, outcome_order)):
        if len(order) < 2:
            reason = (
                f"Column '{name}' has only one category in the compared rows, "
                "so there is no association to test."
            )
            result["test"] = _unavailable(CHI_SQUARE, reason)
            result["association"] = _unavailable(CRAMERS_V, reason)
            return result

    statistic, p_value, dof, expected = chi2_contingency(table, correction=False)
    n = int(table.sum())
    cramers_v = sqrt(statistic / (n * (min(table.shape) - 1)))
    result["test"] = {
        "method": CHI_SQUARE,
        "status": "ok",
        "reason": None,
        "statistic": float(statistic),
        "degrees_of_freedom": int(dof),
        "p_value": float(p_value),
        "continuity_correction": False,
        "expected_counts": np.round(expected, 4).tolist(),
        "expected_count_summary": expected_count_summary(expected),
    }
    result["association"] = {
        "method": CRAMERS_V,
        "status": "ok",
        "reason": None,
        "value": min(1.0, float(cramers_v)),
    }
    result["warnings"].extend(_expected_count_warnings(expected))
    return result
