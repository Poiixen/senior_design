"""Skewness-based distribution descriptions for numeric columns (Ticket #57)."""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from backend.diagnostics.distribution_shape import describe_distribution_shape
from backend.diagnostics.generic_dataset_profiler import profile_dataset

RIGHT = pd.Series(np.random.RandomState(1).exponential(2.0, 200))
LEFT = -RIGHT
SYMMETRIC = pd.Series(np.random.RandomState(2).normal(0, 1, 200))


@pytest.mark.parametrize(
    ("values", "classification"),
    [(RIGHT, "right_skewed"), (LEFT, "left_skewed"), (SYMMETRIC, "approximately_symmetric")],
)
def test_skewness_matches_scipy_and_is_classified(values, classification):
    shape = describe_distribution_shape(values)

    assert shape["status"] == "ok"
    assert shape["skewness"] == pytest.approx(stats.skew(values, bias=False))
    assert shape["sample_size"] == 200
    assert shape["classification"] == classification
    assert shape["warnings"] == []


def test_strength_follows_documented_thresholds():
    assert describe_distribution_shape(RIGHT)["strength"] == "strong"
    assert describe_distribution_shape(SYMMETRIC)["strength"] is None
    # A mild right skew between 0.5 and 1.
    mild = pd.Series(np.random.RandomState(3).gamma(8.0, 1.0, 400))
    shape = describe_distribution_shape(mild)
    assert 0.5 <= shape["skewness"] < 1
    assert (shape["classification"], shape["strength"]) == ("right_skewed", "moderate")


def test_only_finite_values_are_used():
    values = pd.Series([1.0, 2.0, 3.0, 10.0, np.nan, np.inf, -np.inf])

    shape = describe_distribution_shape(values)

    assert shape["sample_size"] == 4
    assert shape["skewness"] == pytest.approx(stats.skew([1, 2, 3, 10], bias=False))
    assert "unstable" in shape["warnings"][0]


def test_standard_error_uses_the_normal_sample_formula():
    n = 200
    expected = np.sqrt(6 * n * (n - 1) / ((n - 2) * (n + 1) * (n + 3)))
    assert describe_distribution_shape(SYMMETRIC)["standard_error"] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("values", "needle"),
    [
        (pd.Series([4.0, 4.0, 4.0, 4.0]), "identical"),
        (pd.Series([1.0, 2.0, np.nan]), "at least 3"),
        (pd.Series([], dtype=float), "at least 3"),
        (pd.Series([True, False, True, True]), "Boolean"),
    ],
)
def test_constant_short_and_boolean_columns_are_unavailable(values, needle):
    shape = describe_distribution_shape(values)

    assert shape["status"] == "unavailable"
    assert needle in shape["reason"]
    assert shape["skewness"] is None and shape["classification"] is None


def test_symmetry_is_not_presented_as_normality():
    shape = describe_distribution_shape(SYMMETRIC)
    assert any("does not mean the values are normally distributed" in text for text in shape["limitations"])
    assert "0.5" in shape["measure"]["thresholds"]["approximately_symmetric"]


def test_profiles_add_shape_and_keep_the_histogram():
    df = pd.DataFrame({"income": RIGHT, "label": ["x"] * 200})

    profile = profile_dataset(df)

    numeric, categorical = profile["column_details"]
    assert numeric["histogram"]["included_values"] == 200
    assert numeric["distribution_shape"]["classification"] == "right_skewed"
    assert "distribution_shape" not in categorical
