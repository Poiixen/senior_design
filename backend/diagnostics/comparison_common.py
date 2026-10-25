"""Column checks and label handling shared by the comparison diagnostics."""

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

# Comparisons refuse columns with more categories than this among the rows
# they use, so contingency tables and group summaries stay readable.
MAX_COMPARISON_CATEGORIES = 100
MAX_CONTINGENCY_CELLS = 10_000
WARN_CONTINGENCY_CELLS = 2_500

DESIGN_NOTE = (
    "Each row is treated as an independent observation. Paired or repeated "
    "measurements of the same subject are not supported."
)


class ComparisonError(ValueError):
    """The requested columns cannot be compared; the message says why."""


def json_label(value):
    """Return a category label as a JSON-safe scalar, keeping its type."""
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return str(value)
    return value


def is_categorical(column: pd.Series) -> bool:
    """Booleans and non-numeric columns can be analysed as categories."""
    return is_bool_dtype(column) or not is_numeric_dtype(column)


def require_column(df: pd.DataFrame, name: str) -> pd.Series:
    if name not in df.columns:
        raise ComparisonError(f"Column '{name}' does not exist in this dataset.")
    return df[name]


def require_categorical(df: pd.DataFrame, name: str) -> pd.Series:
    column = require_column(df, name)
    if not is_categorical(column):
        raise ComparisonError(
            f"Column '{name}' is numeric ({column.dtype}), so it cannot be "
            "used as a categorical column."
        )
    return column


def ordered_counts(column: pd.Series) -> pd.Series:
    """Non-missing value counts, largest first; ties sort by label text."""
    counts = column.dropna().value_counts(sort=False)
    # Categorical dtypes also list categories that never occur.
    counts = counts[counts > 0]
    order = sorted(counts.index, key=lambda label: (-int(counts[label]), str(label)))
    # reindex, not .loc: .loc would read boolean labels as a row mask.
    return counts.reindex(order)


def row_counts(total: int, included: int, **reasons: int) -> dict:
    """Included/excluded row counts. A row can match several reasons."""
    return {
        "total": total,
        "included": included,
        "excluded": total - included,
        "exclusion_reasons": reasons,
    }
