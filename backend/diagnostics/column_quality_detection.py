"""
Column quality diagnostics: constant, near-constant and mixed-type columns.
These checks flag columns that pass validation but are still "suspicious".
They only report issues; the input DataFrame is never modified.

Returns that are:
    constant: Every non-null value in the column is the same, and are at least 2
        i.e.
            Flagged: USA, USA, USA, USA
            Flagged: USA, null, USA, null, USA (the nulls are ignored)
    
    near_constant: The column has at least 2 different values, and the most
        common one makes up 95% or more of the non-null values
        i.e.
            Flagged: 19 * Active, 1 * Inactive (exactly 95%)
            Not flagged: 18 * Active, 2 * Inactive (90%)

    mixed_numeric: Text column with at least 4 values, where at least 75% can be
        read as numbers but at least one can't (blank strings count as missing)
        i.e.
            Flagged: "50000", "52000", "unknown", "48000" (75% numbers, 1 bad value)
            Not flagged: "50000", "52000", "51000", "48000" (all numbers)
            Not flagged: "A", "B", "C", "1", "2" (only 40% numbers)

    mixed_date: Text column with at least 4 values, where at least 80% are dates
        but at least one isn't. A value only counts as a date if it looks like a
        numeric date (2024-01-31, 01/31/2024, 31.01.24) and is a real date
        i.e.
            Flagged: 9 dates in the form 2024-01-01, plus "not a date"
            Flagged: 9 dates in the form 01/01/2024, plus "13/45/2024" (no month 13)
            Not flagged: "May", "June", "today" (words never count as dates)
"""

import re
import warnings
from typing import Optional

import pandas as pd
from pandas.api.types import is_object_dtype, is_string_dtype

# Share of non-null values one value must reach for a near-constant finding.
NEAR_CONSTANT_THRESHOLD = 0.95

# Share of non-null values that must parse as numbers for a mixed-numeric finding.
NUMERIC_LIKE_THRESHOLD = 0.75

# Date detection is stricter so ordinary text columns are not treated as dates.
DATE_LIKE_THRESHOLD = 0.8

# Columns with fewer non-null values than this are too small to judge.
MIN_NON_NULL_VALUES = 2
MIN_VALUES_FOR_TYPE_CHECK = 4

# How many distinct offending values to keep in a finding's metadata.
MAX_EXAMPLE_VALUES = 5 


_DATE_PATTERN = re.compile(
    r"^(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})"
    r"([ T]\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?\s*([AaPp][Mm]|Z|[+-]\d{2}:?\d{2})?)?$"
)


def _finding(column: str, value: float, message: str, recommendation: str, metadata: dict) -> dict:
    return {
        "diagnostic": "column_quality",
        "column": column,
        "severity": "warning",
        "value": value,
        "message": message,
        "recommendation": recommendation,
        "metadata": metadata,
    }


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _is_text_column(series: pd.Series) -> bool:
    return is_object_dtype(series) or (
        is_string_dtype(series) and not isinstance(series.dtype, pd.CategoricalDtype)
    )


def _text_values(series: pd.Series) -> pd.Series:
    values = series.dropna().astype(str).str.strip()
    return values[values != ""]


def _examples(values: pd.Series) -> list:
    return [str(value) for value in values.unique()[:MAX_EXAMPLE_VALUES]]


def _detect_constant_column(column: str, series: pd.Series) -> Optional[dict]:
    values = series.dropna()
    if len(values) < MIN_NON_NULL_VALUES or values.nunique() != 1:
        return None

    return _finding(
        column,
        100.0,
        f"Column '{column}' contains only one distinct non-null value.",
        "Review whether this column provides useful information.",
        {
            "issue": "constant",
            "dominant_value": str(values.iloc[0]),
            "dominant_value_percentage": 100.0,
        },
    )


def _detect_near_constant_column(
    column: str, series: pd.Series, threshold: float = NEAR_CONSTANT_THRESHOLD
) -> Optional[dict]:
    values = series.dropna()
    if len(values) < MIN_NON_NULL_VALUES:
        return None

    counts = values.value_counts()
    if len(counts) < 2:
        return None  # constant columns are reported by _detect_constant_column

    dominant_count = int(counts.iloc[0])
    dominant_share = dominant_count / len(values)
    if dominant_share < threshold:
        return None

    dominant_percentage = dominant_share * 100
    return _finding(
        column,
        dominant_percentage,
        (
            f"Value '{counts.index[0]}' accounts for {dominant_percentage:.2f}% "
            f"of non-null values in '{column}'."
        ),
        "Review whether this column has enough variation to be useful.",
        {
            "issue": "near_constant",
            "dominant_value": str(counts.index[0]),
            "dominant_count": dominant_count,
            "dominant_value_percentage": dominant_percentage,
            "threshold_percentage": threshold * 100,
        },
    )


def _numeric_mask(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").notna()


def _detect_numeric_like_column(column: str, series: pd.Series) -> Optional[dict]:
    if not _is_text_column(series):
        return None

    values = _text_values(series)
    if len(values) < MIN_VALUES_FOR_TYPE_CHECK:
        return None

    numeric = _numeric_mask(values)
    numeric_share = numeric.mean()
    if numeric_share < NUMERIC_LIKE_THRESHOLD or numeric_share == 1:
        return None

    inconsistent = values[~numeric]
    inconsistent_count = len(inconsistent)
    inconsistent_percentage = inconsistent_count / len(values) * 100
    return _finding(
        column,
        inconsistent_percentage,
        (
            f"{_plural(inconsistent_count, 'value', 'values')} in '{column}' "
            f"{'does' if inconsistent_count == 1 else 'do'} not match the "
            "dominant numeric pattern."
        ),
        "Review inconsistent values before numerical analysis.",
        {
            "issue": "mixed_numeric",
            "inconsistent_count": inconsistent_count,
            "inconsistent_percentage": inconsistent_percentage,
            "example_values": _examples(inconsistent),
        },
    )


def _date_mask(values: pd.Series) -> pd.Series:
    # Parse in one vectorized call; per-value parsing took ~35s on 200k rows.
    # format="mixed" infers each value's format independently, and utc=True
    # keeps a mix of timezone-aware and naive values from raising.
    looks_like_date = values.str.match(_DATE_PATTERN).astype(bool)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(
            values.where(looks_like_date), errors="coerce", format="mixed", utc=True
        )
    return parsed.notna()


def _detect_date_like_column(column: str, series: pd.Series) -> Optional[dict]:
    if not _is_text_column(series):
        return None

    values = _text_values(series)
    if len(values) < MIN_VALUES_FOR_TYPE_CHECK:
        return None

    is_date = _date_mask(values)
    date_share = is_date.mean()
    if date_share < DATE_LIKE_THRESHOLD or date_share == 1:
        return None

    inconsistent = values[~is_date]
    inconsistent_count = len(inconsistent)
    inconsistent_percentage = inconsistent_count / len(values) * 100
    return _finding(
        column,
        inconsistent_percentage,
        (
            f"{_plural(inconsistent_count, 'value', 'values')} in '{column}' "
            f"{'does' if inconsistent_count == 1 else 'do'} not match the "
            "dominant date pattern."
        ),
        "Review inconsistent values before parsing this column as dates.",
        {
            "issue": "mixed_date",
            "inconsistent_count": inconsistent_count,
            "inconsistent_percentage": inconsistent_percentage,
            "example_values": _examples(inconsistent),
        },
    )


def detect_column_quality(df: pd.DataFrame) -> list[dict]:
    """Return column quality findings for every column in ``df``."""
    findings = []
    # Select by position: df[name] returns a DataFrame when names repeat.
    for position, column in enumerate(df.columns):
        series = df.iloc[:, position]
        name = str(column)
        for detector in (
            _detect_constant_column,
            _detect_near_constant_column,
            _detect_numeric_like_column,
            _detect_date_like_column,
        ):
            finding = detector(name, series)
            if finding is not None:
                findings.append(finding)
    return findings
