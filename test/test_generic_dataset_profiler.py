"""Tests for the generic dataset profiler."""

import json
import math

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

    # Check existing fields without requiring exact dictionary equality
    assert details[0]["name"] == "id"
    assert details[0]["dtype"] == "int64"
    assert details[0]["category"] == "numeric"
    assert details[0]["unique_values"] == 6

    assert details[2]["name"] == "group"
    assert details[2]["dtype"] == "object"
    assert details[2]["category"] == "categorical"
    assert details[2]["unique_values"] == 3


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
    reported = [
        r["column_name"]
        for r in profile_dataset(missing_values_df)["missing_values"]
    ]

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


# --------------------------------------------------
# New tests for Ticket #33
# --------------------------------------------------


def test_numeric_column_statistics():
    df = pd.DataFrame({
        "age": [20, 30, 40, 50, 60]
    })

    details = profile_dataset(df)["column_details"][0]

    assert details["category"] == "numeric"
    assert details["non_null_count"] == 5
    assert details["missing_count"] == 0
    assert details["missing_percentage"] == 0.0
    assert details["unique_values"] == 5
    assert details["unique_percentage"] == 100.0

    assert details["mean"] == pytest.approx(40.0)
    assert details["median"] == pytest.approx(40.0)
    assert details["std_dev"] == pytest.approx(15.8113883)
    assert details["min"] == pytest.approx(20.0)
    assert details["q1"] == pytest.approx(30.0)
    assert details["q3"] == pytest.approx(50.0)
    assert details["max"] == pytest.approx(60.0)
    assert details["histogram"]["included_values"] == 5
    assert sum(details["histogram"]["counts"]) == 5
    assert len(details["histogram"]["bin_edges"]) == len(details["histogram"]["counts"]) + 1


def test_histogram_handles_constant_and_unusable_numeric_columns():
    constant = profile_dataset(pd.DataFrame({"score": [4, 4, 4]}))["column_details"][0]["histogram"]
    empty = profile_dataset(pd.DataFrame({
        "score": pd.Series([None, float("inf")], dtype="float64")
    }))["column_details"][0]["histogram"]

    assert constant["counts"] == [3]
    assert constant["bin_edges"][0] < 4 < constant["bin_edges"][1]
    assert empty == {"included_values": 0, "bin_edges": [], "counts": []}


def test_categorical_column_statistics():
    df = pd.DataFrame({
        "occupation": [
            "Engineer",
            "Doctor",
            "Engineer",
            "Teacher",
            "Engineer"
        ]
    })

    details = profile_dataset(df)["column_details"][0]

    assert details["category"] == "categorical"
    assert details["non_null_count"] == 5
    assert details["missing_count"] == 0
    assert details["missing_percentage"] == 0.0
    assert details["unique_values"] == 3
    assert details["unique_percentage"] == 60.0

    assert details["most_common_value"] == "Engineer"
    assert details["most_common_count"] == 3
    assert details["most_common_percentage"] == 60.0


def test_missing_count_and_percentage():
    df = pd.DataFrame({
        "age": [20, None, 40, None]
    })

    details = profile_dataset(df)["column_details"][0]

    assert details["non_null_count"] == 2
    assert details["missing_count"] == 2
    assert details["missing_percentage"] == 50.0


def test_unique_percentage_uses_non_null_values():
    df = pd.DataFrame({
        "score": [10, 10, 20, None, None]
    })

    details = profile_dataset(df)["column_details"][0]

    assert details["non_null_count"] == 3
    assert details["unique_values"] == 2
    assert details["unique_percentage"] == pytest.approx(66.67)


def test_numeric_statistics_with_missing_values():
    df = pd.DataFrame({
        "score": [10, 20, None, 30]
    })

    details = profile_dataset(df)["column_details"][0]

    assert details["mean"] == pytest.approx(20.0)
    assert details["median"] == pytest.approx(20.0)
    assert details["min"] == pytest.approx(10.0)
    assert details["max"] == pytest.approx(30.0)

    assert details["non_null_count"] == 3
    assert details["missing_count"] == 1
    assert details["missing_percentage"] == 25.0


def test_categorical_statistics_with_missing_values():
    df = pd.DataFrame({
        "group": ["A", "A", "B", None, None]
    })

    details = profile_dataset(df)["column_details"][0]

    assert details["non_null_count"] == 3
    assert details["missing_count"] == 2
    assert details["missing_percentage"] == 40.0

    assert details["most_common_value"] == "A"
    assert details["most_common_count"] == 2
    assert details["most_common_percentage"] == pytest.approx(66.67)


def test_all_null_numeric_column():
    df = pd.DataFrame({
        "age": pd.Series([None, None, None], dtype="float64")
    })

    details = profile_dataset(df)["column_details"][0]

    assert details["category"] == "numeric"
    assert details["non_null_count"] == 0
    assert details["missing_count"] == 3
    assert details["missing_percentage"] == 100.0
    assert details["unique_values"] == 0
    assert details["unique_percentage"] is None

    assert details["mean"] is None
    assert details["median"] is None
    assert details["std_dev"] is None
    assert details["min"] is None
    assert details["q1"] is None
    assert details["q3"] is None
    assert details["max"] is None


def test_all_null_categorical_column():
    df = pd.DataFrame({
        "group": pd.Series([None, None, None], dtype="object")
    })

    details = profile_dataset(df)["column_details"][0]

    assert details["category"] == "categorical"
    assert details["non_null_count"] == 0
    assert details["missing_count"] == 3
    assert details["missing_percentage"] == 100.0
    assert details["unique_values"] == 0
    assert details["unique_percentage"] is None

    assert details["most_common_value"] is None
    assert details["most_common_count"] is None
    assert details["most_common_percentage"] is None


def test_single_numeric_value():
    df = pd.DataFrame({
        "score": [42]
    })

    details = profile_dataset(df)["column_details"][0]

    assert details["mean"] == pytest.approx(42.0)
    assert details["median"] == pytest.approx(42.0)
    assert details["min"] == pytest.approx(42.0)
    assert details["max"] == pytest.approx(42.0)

    # Sample standard deviation requires at least two values
    assert details["std_dev"] is None


def test_empty_dataframe_with_columns():
    df = pd.DataFrame({
        "score": pd.Series(dtype="float64"),
        "group": pd.Series(dtype="object")
    })

    result = profile_dataset(df)

    assert result["rows"] == 0
    assert result["columns"] == 2

    by_column = {
        d["name"]: d for d in result["column_details"]
    }

    assert by_column["score"]["non_null_count"] == 0
    assert by_column["score"]["missing_count"] == 0
    assert by_column["score"]["missing_percentage"] is None
    assert by_column["score"]["unique_percentage"] is None
    assert by_column["score"]["mean"] is None

    assert by_column["group"]["non_null_count"] == 0
    assert by_column["group"]["missing_count"] == 0
    assert by_column["group"]["missing_percentage"] is None
    assert by_column["group"]["unique_percentage"] is None
    assert by_column["group"]["most_common_value"] is None


def test_boolean_column_statistics():
    df = pd.DataFrame({
        "active": [True, False, True, True]
    })

    result = profile_dataset(df)
    details = result["column_details"][0]

    # Preserve existing Boolean classification
    assert result["numeric_columns"] == ["active"]
    assert details["category"] == "numeric"
    assert details["non_null_count"] == 4
    assert details["missing_count"] == 0
    assert details["unique_values"] == 2
    assert details["unique_percentage"] == 50.0


def test_datetime_column_statistics():
    df = pd.DataFrame({
        "created_at": pd.to_datetime([
            "2026-01-01",
            "2026-01-02",
            "2026-01-02"
        ])
    })

    result = profile_dataset(df)
    details = result["column_details"][0]

    assert result["categorical_columns"] == ["created_at"]
    assert details["category"] == "categorical"
    assert details["non_null_count"] == 3
    assert details["unique_values"] == 2

    assert details["most_common_value"] == "2026-01-02 00:00:00"
    assert details["most_common_count"] == 2
    assert details["most_common_percentage"] == pytest.approx(66.67)


def test_profiler_returns_json_safe_values():
    df = pd.DataFrame({
        "age": [20, 30, None],
        "group": ["A", "B", "A"]
    })

    result = profile_dataset(df)

    # Strict JSON serialization rejects NaN and Infinity
    serialized = json.dumps(result, allow_nan=False)

    assert isinstance(serialized, str)


def test_numeric_infinity_returns_none():
    df = pd.DataFrame({
        "score": [10.0, float("inf"), 20.0]
    })

    details = profile_dataset(df)["column_details"][0]

    # Non-finite statistics must not be returned
    for field in ["mean", "median", "std_dev", "min", "q1", "q3", "max"]:
        value = details[field]
        assert value is None or math.isfinite(value)
