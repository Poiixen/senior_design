"""Tests for IQR outlier detection."""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "diagnostics"))

from backend.diagnostics.iqr_outlier_detection import (
    detect_numeric_outliers,
    detect_outliers_iqr,
)
from backend.ingestion.csv_loader import load_csv

ADULT_DATA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "raw", "UCI_ADULT_INCOME", "adult.data"
)
ADULT_COLUMNS = [
    "age", "workclass", "fnlwgt", "education", "education_num",
    "marital_status", "occupation", "relationship", "race", "sex",
    "capital_gain", "capital_loss", "hours_per_week", "native_country", "income",
]


@pytest.fixture
def no_outlier_df():
    # 1..9: Q1=3, Q3=7, IQR=4, bounds -3..13
    return pd.DataFrame({"a": list(range(1, 10))})


@pytest.fixture
def two_sided_outlier_df():
    # 1..9 plus one low and one high extreme
    return pd.DataFrame({"a": list(range(1, 10)) + [-100, 100]})


@pytest.fixture
def mixed_type_df():
    return pd.DataFrame({
        "num": list(range(1, 10)) + [100],
        "text": ["x"] * 10,
    })


def test_detect_outliers_iqr_computes_quartiles_and_bounds(no_outlier_df):
    result = detect_outliers_iqr(no_outlier_df, "a")

    assert result["column_name"] == "a"
    assert result["q1"] == 3.0
    assert result["q3"] == 7.0
    assert result["iqr"] == 4.0
    assert result["lower_bound"] == -3.0
    assert result["upper_bound"] == 13.0


def test_detect_outliers_iqr_reports_no_outliers_for_clean_column(no_outlier_df):
    result = detect_outliers_iqr(no_outlier_df, "a")

    assert result["outlier_count"] == 0
    assert result["outlier_percentage"] == 0.0


def test_detect_outliers_iqr_counts_low_and_high_outliers(two_sided_outlier_df):
    result = detect_outliers_iqr(two_sided_outlier_df, "a")

    assert result["outlier_count"] == 2
    assert result["outlier_percentage"] == pytest.approx(2 / 11 * 100, rel=1e-6)


def test_detect_outliers_iqr_ignores_missing_values():
    df = pd.DataFrame({"a": list(range(1, 10)) + [100, None]})
    result = detect_outliers_iqr(df, "a")

    # Percentage is over the 10 non-null values, not all 11 rows.
    assert result["outlier_count"] == 1
    assert result["outlier_percentage"] == pytest.approx(10.0)


def test_detect_outliers_iqr_treats_bounds_as_inclusive():
    # 1..9 with a value exactly on the upper bound (13) — not an outlier.
    df = pd.DataFrame({"a": list(range(1, 10))})
    bounds = detect_outliers_iqr(df, "a")

    on_bound = pd.DataFrame({"a": list(range(1, 10)) + [bounds["upper_bound"]]})
    assert detect_outliers_iqr(on_bound, "a")["outlier_count"] == 0


def test_detect_outliers_iqr_handles_constant_column():
    # Zero IQR collapses the bounds onto the single value.
    df = pd.DataFrame({"a": [5] * 10})
    result = detect_outliers_iqr(df, "a")

    assert result["iqr"] == 0.0
    assert result["lower_bound"] == 5.0
    assert result["upper_bound"] == 5.0
    assert result["outlier_count"] == 0


def test_detect_outliers_iqr_handles_all_missing_column():
    df = pd.DataFrame({"a": pd.Series([None, None, None], dtype="float64")})
    result = detect_outliers_iqr(df, "a")

    assert result["outlier_count"] == 0
    assert result["outlier_percentage"] == 0.0
    assert pd.isna(result["q1"])
    assert pd.isna(result["upper_bound"])


def test_detect_outliers_iqr_respects_custom_multiplier():
    # 1..9 plus 20: Q1=3.25, Q3=7.75, IQR=4.5.
    df = pd.DataFrame({"a": list(range(1, 10)) + [20]})

    # 1.5 * IQR puts the upper bound at 14.5, so 20 is an outlier.
    assert detect_outliers_iqr(df, "a")["outlier_count"] == 1

    # 3.0 * IQR ("extreme" outliers only) pushes it to 21.25, so 20 is not.
    assert detect_outliers_iqr(df, "a", multiplier=3.0)["outlier_count"] == 0


def test_detect_outliers_iqr_raises_for_missing_column(no_outlier_df):
    with pytest.raises(KeyError):
        detect_outliers_iqr(no_outlier_df, "does_not_exist")


def test_detect_outliers_iqr_raises_for_non_numeric_column(mixed_type_df):
    with pytest.raises(TypeError):
        detect_outliers_iqr(mixed_type_df, "text")


def test_detect_outliers_iqr_raises_for_negative_multiplier(no_outlier_df):
    with pytest.raises(ValueError):
        detect_outliers_iqr(no_outlier_df, "a", multiplier=-1.0)


def test_detect_numeric_outliers_skips_non_numeric_columns(mixed_type_df):
    results = detect_numeric_outliers(mixed_type_df)

    assert [row["column_name"] for row in results] == ["num"]
    assert results[0]["outlier_count"] == 1


def test_detect_numeric_outliers_returns_row_per_numeric_column():
    df = pd.DataFrame({
        "a": list(range(1, 10)) + [100],
        "b": list(range(1, 11)),
        "label": ["x"] * 10,
    })
    results = detect_numeric_outliers(df)
    results_by_column = {row["column_name"]: row for row in results}

    assert set(results_by_column) == {"a", "b"}
    assert results_by_column["a"]["outlier_count"] == 1
    assert results_by_column["b"]["outlier_count"] == 0


def test_detect_numeric_outliers_returns_empty_list_without_numeric_columns():
    df = pd.DataFrame({"text": ["a", "b"], "other": ["c", "d"]})
    assert detect_numeric_outliers(df) == []


def test_detect_outliers_iqr_on_adult_dataset():
    df = load_csv(
        ADULT_DATA_PATH,
        header=None,
        names=ADULT_COLUMNS,
        na_values="?",
        skipinitialspace=True,
    )

    result = detect_outliers_iqr(df, "age")

    assert result["q1"] == 28.0
    assert result["q3"] == 48.0
    assert result["iqr"] == 20.0
    assert result["lower_bound"] == -2.0
    assert result["upper_bound"] == 78.0
    assert result["outlier_count"] == int((df["age"] > 78).sum())
    assert 0 < result["outlier_percentage"] < 5


def test_detect_numeric_outliers_on_adult_dataset():
    df = load_csv(
        ADULT_DATA_PATH,
        header=None,
        names=ADULT_COLUMNS,
        na_values="?",
        skipinitialspace=True,
    )

    results = detect_numeric_outliers(df)
    reported_columns = [row["column_name"] for row in results]

    assert reported_columns == [
        "age", "fnlwgt", "education_num",
        "capital_gain", "capital_loss", "hours_per_week",
    ]
    for row in results:
        assert 0 <= row["outlier_percentage"] <= 100
