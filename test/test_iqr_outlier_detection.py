"""Tests for IQR outlier detection."""

import pandas as pd
import pytest

from backend.diagnostics.iqr_outlier_detection import (
    detect_numeric_outliers,
    detect_outliers_iqr,
)


def test_computes_quartiles_and_bounds(numeric_outliers_df):
    result = detect_outliers_iqr(numeric_outliers_df, "value")

    assert result["column_name"] == "value"
    assert result["q1"] == 2.5
    assert result["q3"] == 7.5
    assert result["iqr"] == 5.0
    assert result["lower_bound"] == -5.0
    assert result["upper_bound"] == 15.0


def test_counts_low_and_high_outliers(numeric_outliers_df):
    result = detect_outliers_iqr(numeric_outliers_df, "value")

    assert result["outlier_count"] == 2
    assert result["outlier_percentage"] == pytest.approx(2 / 11 * 100)


def test_clean_column_reports_no_outliers(numeric_outliers_df):
    result = detect_outliers_iqr(numeric_outliers_df, "clean")

    assert result["outlier_count"] == 0
    assert result["outlier_percentage"] == 0.0


def test_percentage_is_over_non_null_values_only():
    df = pd.DataFrame({"a": list(range(1, 10)) + [100, None]})

    result = detect_outliers_iqr(df, "a")

    assert result["outlier_count"] == 1
    assert result["outlier_percentage"] == pytest.approx(10.0)


def test_value_exactly_on_bound_is_not_an_outlier():
    df = pd.DataFrame({"a": list(range(1, 10))})
    upper = detect_outliers_iqr(df, "a")["upper_bound"]

    on_bound = pd.DataFrame({"a": list(range(1, 10)) + [upper]})
    assert detect_outliers_iqr(on_bound, "a")["outlier_count"] == 0


def test_constant_column_collapses_bounds():
    result = detect_outliers_iqr(pd.DataFrame({"a": [5] * 10}), "a")

    assert result["iqr"] == 0.0
    assert result["lower_bound"] == 5.0
    assert result["upper_bound"] == 5.0
    assert result["outlier_count"] == 0


def test_all_missing_column_returns_nan_bounds():
    df = pd.DataFrame({"a": pd.Series([None, None, None], dtype="float64")})

    result = detect_outliers_iqr(df, "a")

    assert result["outlier_count"] == 0
    assert result["outlier_percentage"] == 0.0
    assert pd.isna(result["q1"])
    assert pd.isna(result["upper_bound"])


def test_larger_multiplier_widens_the_bounds():
    # 1..9 plus 20: IQR=4.5, so 1.5x cuts at 14.5 but 3.0x cuts at 21.25.
    df = pd.DataFrame({"a": list(range(1, 10)) + [20]})

    assert detect_outliers_iqr(df, "a")["outlier_count"] == 1
    assert detect_outliers_iqr(df, "a", multiplier=3.0)["outlier_count"] == 0


def test_zero_multiplier_flags_everything_outside_the_quartiles():
    df = pd.DataFrame({"a": list(range(1, 10))})

    result = detect_outliers_iqr(df, "a", multiplier=0)

    assert result["lower_bound"] == 3.0
    assert result["upper_bound"] == 7.0
    assert result["outlier_count"] == 4


def test_missing_column_raises_key_error(simple_clean_df):
    with pytest.raises(KeyError):
        detect_outliers_iqr(simple_clean_df, "does_not_exist")


def test_non_numeric_column_raises_type_error(numeric_outliers_df):
    with pytest.raises(TypeError):
        detect_outliers_iqr(numeric_outliers_df, "label")


def test_negative_multiplier_raises_value_error(simple_clean_df):
    with pytest.raises(ValueError):
        detect_outliers_iqr(simple_clean_df, "score", multiplier=-1.0)


def test_sweep_skips_non_numeric_columns(numeric_outliers_df):
    results = detect_numeric_outliers(numeric_outliers_df)

    assert [r["column_name"] for r in results] == ["value", "clean"]
    assert results[0]["outlier_count"] == 2
    assert results[1]["outlier_count"] == 0


def test_sweep_skips_bool_columns(mixed_types_df):
    # select_dtypes('number') excludes bool, unlike the profiler.
    results = detect_numeric_outliers(mixed_types_df)

    assert [r["column_name"] for r in results] == ["int_col", "float_col"]


def test_sweep_returns_empty_list_without_numeric_columns():
    df = pd.DataFrame({"text": ["a", "b"], "other": ["c", "d"]})

    assert detect_numeric_outliers(df) == []


def test_sweep_forwards_the_multiplier():
    df = pd.DataFrame({"a": list(range(1, 10)) + [20]})

    assert detect_numeric_outliers(df)[0]["outlier_count"] == 1
    assert detect_numeric_outliers(df, multiplier=3.0)[0]["outlier_count"] == 0
