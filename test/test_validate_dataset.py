"""Tests for dataset structure validation."""

import pandas as pd

from backend.diagnostics.validate_dataset import validate_dataset


def test_clean_dataset_is_valid(simple_clean_df):
    assert validate_dataset(simple_clean_df) == {
        "valid": True,
        "rows": 6,
        "columns": 3,
        "warnings": [],
    }


def test_mixed_types_dataset_is_valid(mixed_types_df):
    result = validate_dataset(mixed_types_df)

    assert result["valid"] is True
    assert result["rows"] == 5
    assert result["columns"] == 5


def test_empty_dataframe_warns_on_rows_and_columns():
    result = validate_dataset(pd.DataFrame())

    assert result["valid"] is False
    assert "Dataset is empty" in result["warnings"]
    assert "Dataset has zero columns" in result["warnings"]


def test_duplicate_column_names_are_reported():
    df = pd.DataFrame(
        [["Alice", 20, "NY"], ["Bob", 21, "FL"], ["Cara", 22, "TX"],
         ["Dan", 23, "CA"], ["Eve", 24, "MA"]],
        columns=["name", "age", "name"],
    )

    result = validate_dataset(df)

    assert result["valid"] is False
    assert "Duplicate column names found: ['name'], count: 1" in result["warnings"]


def test_completely_empty_column_is_reported(simple_clean_df):
    df = simple_clean_df.assign(blank=None)

    result = validate_dataset(df)

    assert result["valid"] is False
    assert "Completely empty columns found: ['blank']" in result["warnings"]


def test_partially_empty_column_is_not_reported(missing_values_df):
    result = validate_dataset(missing_values_df)

    assert result["valid"] is True
    assert result["warnings"] == []


def test_fewer_than_five_rows_warns(simple_clean_df):
    result = validate_dataset(simple_clean_df.head(4))

    assert result["valid"] is False
    assert "Dataset is extremely small (fewer than 5 rows)" in result["warnings"]


def test_exactly_five_rows_does_not_warn(simple_clean_df):
    result = validate_dataset(simple_clean_df.head(5))

    assert result["valid"] is True
    assert result["warnings"] == []


def test_multiple_problems_are_all_reported():
    df = pd.DataFrame({"a": [1, 2], "b": [None, None]})

    result = validate_dataset(df)

    assert result["valid"] is False
    assert len(result["warnings"]) == 2
