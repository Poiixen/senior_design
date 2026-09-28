"""Integration tests: real UCI Adult data through the full pipeline.

Every diagnostic is exercised end to end against data/raw, so these
catch regressions the synthetic unit tests cannot. Skipped when the
raw dataset is not checked out.
"""

import pandas as pd
import pytest

from backend.diagnostics.duplicate_detection import detect_duplicates
from backend.diagnostics.generic_dataset_profiler import profile_dataset
from backend.diagnostics.iqr_outlier_detection import (
    detect_numeric_outliers,
    detect_outliers_iqr,
)
from backend.diagnostics.missing_value_detection import detect_missing_values
from backend.diagnostics.validate_dataset import validate_dataset
from backend.ingestion.adult_adapter import ADULT_COLUMNS, ADULT_NUMERIC_COLUMNS

pytestmark = pytest.mark.integration


# --- Adapter ----------------------------------------------------------


def test_train_file_has_expected_shape_and_labels(adult_df):
    assert list(adult_df.columns) == ADULT_COLUMNS
    assert len(adult_df) == 32561
    assert set(adult_df["income"]) == {"<=50K", ">50K"}


def test_test_file_has_expected_shape_and_labels(adult_test_df):
    assert list(adult_test_df.columns) == ADULT_COLUMNS
    assert len(adult_test_df) == 16281
    # Trailing periods in adult.test must be stripped to match train.
    assert set(adult_test_df["income"]) == {"<=50K", ">50K"}


def test_numeric_columns_are_parsed_as_numbers(adult_df):
    for column in ADULT_NUMERIC_COLUMNS:
        assert pd.api.types.is_numeric_dtype(adult_df[column]), column


def test_no_surrounding_whitespace_survives_the_adapter(adult_df):
    stringified = adult_df.astype(str)
    assert not stringified.apply(lambda col: col.str.contains(r"^\s|\s$")).any().any()


# --- Diagnostics ------------------------------------------------------


def test_validate_reports_a_healthy_dataset(adult_df):
    assert validate_dataset(adult_df) == {
        "valid": True,
        "rows": 32561,
        "columns": 15,
        "warnings": [],
    }


def test_profile_splits_numeric_and_categorical_columns(adult_df):
    result = profile_dataset(adult_df)

    assert result["rows"] == 32561
    assert result["columns"] == 15
    assert result["numeric_columns"] == ADULT_NUMERIC_COLUMNS
    assert "income" in result["categorical_columns"]
    assert len(result["column_details"]) == 15


def test_missing_values_match_the_documented_counts(adult_df):
    by_column = {r["column_name"]: r for r in detect_missing_values(adult_df)}

    # "?" placeholders appear in exactly these three columns.
    assert set(by_column) == {"workclass", "occupation", "native_country"}
    assert by_column["workclass"]["missing_count"] == 1836
    assert by_column["workclass"]["severity"] == "moderate"
    assert by_column["occupation"]["missing_count"] == 1843
    assert by_column["occupation"]["severity"] == "moderate"
    assert by_column["native_country"]["missing_count"] == 583
    assert by_column["native_country"]["severity"] == "low"


def test_duplicate_rows_match_the_documented_count(adult_df):
    result = detect_duplicates(adult_df)

    assert result["duplicate_count"] == 24
    assert result["duplicate_percentage"] == pytest.approx(0.0737, rel=1e-2)


def test_age_outlier_bounds(adult_df):
    result = detect_outliers_iqr(adult_df, "age")

    assert result["q1"] == 28.0
    assert result["q3"] == 48.0
    assert result["iqr"] == 20.0
    assert result["lower_bound"] == -2.0
    assert result["upper_bound"] == 78.0
    assert result["outlier_count"] == 143


def test_outlier_sweep_covers_every_numeric_column(adult_df):
    results = detect_numeric_outliers(adult_df)

    assert [r["column_name"] for r in results] == ADULT_NUMERIC_COLUMNS
    for row in results:
        assert 0 <= row["outlier_percentage"] <= 100
