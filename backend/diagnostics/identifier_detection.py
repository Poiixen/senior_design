"""Flag columns that look like row identifiers, for the user to review.

A flag is a prompt to check, never a classification: nothing is dropped or
blocked, and the user can confirm that a flagged column is meaningful.

Signals, all documented in the returned ``reasons`` and ``signals``:

* Distinctness: at least ``DISTINCT_RATIO_FLAG`` (90%) of the non-missing
  values are different from each other, so nearly every row has its own
  value. This alone is enough to flag a text column.
* Name: a word of the column name (split on punctuation, underscores and
  camelCase) is one of ``NAME_WORDS``. A name alone never flags a column; it
  must be paired with at least ``NAME_RATIO_FLAG`` (50%) distinct values.

Columns need ``MINIMUM_ROWS`` non-missing values before they are judged, and
only categorical columns (or integer columns with an identifier-like name)
are considered. A column with many categories that repeat, such as a city or
product code, is not flagged only for having many categories.
"""

import re
from typing import Optional

import pandas as pd
from pandas.api.types import is_integer_dtype

from backend.diagnostics.comparison_common import is_categorical

DISTINCT_RATIO_FLAG = 0.9
NAME_RATIO_FLAG = 0.5
MINIMUM_ROWS = 10
NAME_WORDS = ("id", "uuid", "guid", "key", "index", "idx", "serial", "hash", "identifier", "ref")

NOTE = (
    "This is a review flag based on the signals above, not a classification. "
    "Confirm the column if it is a meaningful grouping."
)


def _name_words(name: str) -> list:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(name))
    words = re.split(r"[^A-Za-z0-9]+", spaced.lower())
    return [word for word in words if word in NAME_WORDS]


def review_identifier_column(name: str, column: pd.Series) -> Optional[dict]:
    """Return the review for ``column``, or None when it is not a candidate."""
    words = _name_words(name)
    if not (is_categorical(column) or (is_integer_dtype(column) and words)):
        return None

    values = column.dropna()
    non_missing = int(len(values))
    distinct = int(values.nunique())
    ratio = distinct / non_missing if non_missing else 0.0
    signals = {
        "non_missing_values": non_missing,
        "distinct_values": distinct,
        "distinct_ratio": round(ratio, 4),
        "name_words": words,
        "minimum_rows": MINIMUM_ROWS,
    }
    reasons = []
    if non_missing >= MINIMUM_ROWS:
        if ratio >= DISTINCT_RATIO_FLAG:
            reasons.append(
                f"{distinct} of {non_missing} non-missing values are distinct "
                f"({ratio:.0%}), so nearly every row has its own value."
            )
        if words and ratio >= NAME_RATIO_FLAG:
            reasons.append(
                "The column name contains identifier-like word(s): "
                + ", ".join(words) + f", and {ratio:.0%} of its values are distinct."
            )
    return {
        "column": str(name),
        "likely_identifier": bool(reasons),
        "reasons": reasons,
        "signals": signals,
        "note": NOTE,
    }


def flagged_identifier_reviews(df: pd.DataFrame, columns: list) -> list:
    """Reviews, in the order given, for the named columns that are flagged."""
    reviews = (review_identifier_column(name, df[name]) for name in columns if name in df.columns)
    return [review for review in reviews if review and review["likely_identifier"]]
