"""Tests for the generic dataset profiler."""

import pandas as pd
import pytest

from backend.diagnostics.generic_dataset_profiler import profile_dataset


def test_reports_shape_and_column_split(simple_clean_df):
    result = profile_dataset(simple_clean_df)

    assert result["rows"] == 6
    assert result["columns"] == 3
    assert result["numeric_columns"] == ["id", "score"]
    assert result["categorical_columns"] == ["group"]


def test_column_details_follow_dataframe_order(simple_clean_df):
    details = profile_dataset(simple_clean_df)["column_details"]

    assert [d["name"] for d in details] == ["id", "score", "group"]
    assert details[0] == {
        "name": "id",
        "dtype": "int64",
        "category": "numeric",
        "unique_values": 6,
    }
    assert details[2] == {
        "name": "group",
        "dtype": "object",
        "category": "categorical",
        "unique_values": 3,
    }


def test_bools_count_as_numeric_and_dates_as_categorical(mixed_types_df):
    result = profile_dataset(mixed_types_df)

    assert result["numeric_columns"] == ["int_col", "float_col", "bool_col"]
    assert result["categorical_columns"] == ["str_col", "date_col"]


def test_unique_values_ignore_missing(missing_values_df):
    by_column = {
        d["name"]: d for d in profile_dataset(missing_values_df)["column_details"]
    }

    assert by_column["complete"]["unique_values"] == 100
    assert by_column["high"]["unique_values"] == 60


def test_embeds_duplicate_report(duplicate_rows_df):
    result = profile_dataset(duplicate_rows_df)

    assert result["duplicates"]["duplicate_count"] == 2
    assert result["duplicates"]["duplicate_percentage"] == pytest.approx(25.0)


def test_embeds_missing_value_report(missing_values_df):
    reported = [r["column_name"] for r in profile_dataset(missing_values_df)["missing_values"]]

    assert reported == ["low", "moderate", "high"]


def test_clean_dataset_reports_no_problems(simple_clean_df):
    result = profile_dataset(simple_clean_df)

    assert result["duplicates"]["duplicate_count"] == 0
    assert result["missing_values"] == []


def test_empty_dataframe_profiles_without_error():
    result = profile_dataset(pd.DataFrame())

    assert result["rows"] == 0
    assert result["columns"] == 0
    assert result["numeric_columns"] == []
    assert result["categorical_columns"] == []
    assert result["column_details"] == []
    assert result["missing_values"] == []
