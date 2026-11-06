"""Describe the shape of a numeric column with a skewness measure.

Skewness is the adjusted Fisher-Pearson standardized moment coefficient G1,
the sample-size-corrected estimator reported by pandas ``Series.skew`` and
``scipy.stats.skew(bias=False)``:

    g1 = m3 / m2 ** 1.5                 (m2, m3: central moments, divided by n)
    G1 = g1 * sqrt(n * (n - 1)) / (n - 2)

Only finite values are used. The classification follows Bulmer (1979):

    |G1| < 0.5         approximately symmetric
    0.5 <= |G1| < 1    moderately skewed (left if negative, right if positive)
    |G1| >= 1          strongly skewed

Approximate symmetry is not normality: a uniform or two-peaked distribution
can have a skewness near zero.
"""

import math

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype

SYMMETRIC_BELOW = 0.5
STRONG_FROM = 1.0
MIN_VALUES = 3
# Below this many values the estimate is unstable; a warning says so.
STABLE_FROM = 50

MEASURE = {
    "key": "adjusted_fisher_pearson_skewness",
    "name": "Adjusted Fisher-Pearson skewness coefficient (G1)",
    "calculation": (
        "G1 = g1 * sqrt(n * (n - 1)) / (n - 2), where g1 = m3 / m2^1.5 and "
        "m2, m3 are the second and third central moments of the finite values. "
        "Matches pandas Series.skew and scipy.stats.skew(bias=False)."
    ),
    "thresholds": {
        "approximately_symmetric": "|skewness| < 0.5",
        "moderate": "0.5 <= |skewness| < 1",
        "strong": "|skewness| >= 1",
        "direction": "negative is left-skewed (long tail of small values); "
        "positive is right-skewed (long tail of large values)",
        "source": "Bulmer (1979), Principles of Statistics",
    },
}

LIMITATIONS = [
    "Approximate symmetry does not mean the values are normally distributed; "
    "flat or two-peaked distributions can also have skewness near zero.",
    "Skewness is sensitive to a few extreme values; check the histogram and "
    "outlier counts alongside it.",
    "Missing, NaN and infinite values are left out.",
]


def _standard_error(n: int) -> float:
    """Standard error of G1 for a sample of n values from a normal population."""
    return math.sqrt(6 * n * (n - 1) / ((n - 2) * (n + 1) * (n + 3)))


def _unavailable(n: int, reason: str) -> dict:
    return {
        "status": "unavailable",
        "reason": reason,
        "measure": MEASURE,
        "sample_size": n,
        "skewness": None,
        "standard_error": None,
        "classification": None,
        "strength": None,
        "warnings": [],
        "limitations": LIMITATIONS,
    }


def describe_distribution_shape(column: pd.Series) -> dict:
    """Skewness, classification and caveats for the finite values of ``column``."""
    if is_bool_dtype(column):
        return _unavailable(
            int(column.count()),
            "Boolean columns hold only two values, so skewness does not describe "
            "their shape usefully. Use the value counts instead.",
        )
    values = pd.to_numeric(column, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
    values = values[np.isfinite(values)]
    n = int(len(values))
    if n < MIN_VALUES:
        return _unavailable(
            n,
            f"Skewness needs at least {MIN_VALUES} finite values; this column has {n}.",
        )
    if np.ptp(values) == 0:
        return _unavailable(
            n,
            "Every finite value is identical, so the column has no spread and "
            "skewness is undefined.",
        )

    skewness = float(pd.Series(values).skew())
    magnitude = abs(skewness)
    if magnitude < SYMMETRIC_BELOW:
        classification, strength = "approximately_symmetric", None
    else:
        classification = "right_skewed" if skewness > 0 else "left_skewed"
        strength = "strong" if magnitude >= STRONG_FROM else "moderate"

    standard_error = _standard_error(n)
    warnings = []
    if n < STABLE_FROM:
        warnings.append(
            f"Only {n} values were used; with fewer than {STABLE_FROM} the "
            f"skewness estimate is unstable (standard error about {standard_error:.2f}), "
            "so treat the classification as tentative."
        )
    return {
        "status": "ok",
        "reason": None,
        "measure": MEASURE,
        "sample_size": n,
        "skewness": skewness,
        "standard_error": standard_error,
        "classification": classification,
        "strength": strength,
        "warnings": warnings,
        "limitations": LIMITATIONS,
    }
