"""Tests for missing value detection."""

import pandas as pd
import pytest

from backend.diagnostics.missing_value_detection import (
    classify_severity,
    detect_missing_values,
)


def test_no_missing_values_returns_empty_list(simple_clean_df):
    assert detect_missing_values(simple_clean_df) == []


def test_columns_without_missing_values_are_excluded(missing_values_df):
    reported = [row["column_name"] for row in detect_missing_values(missing_values_df)]

    assert reported == ["low", "moderate", "high"]


def test_reports_count_percentage_and_severity(missing_values_df):
    by_column = {r["column_name"]: r for r in detect_missing_values(missing_values_df)}

    assert by_column["low"]["missing_count"] == 3
    assert by_column["low"]["missing_percentage"] == pytest.approx(3.0)
    assert by_column["low"]["severity"] == "low"

    assert by_column["moderate"]["missing_count"] == 10
    assert by_column["moderate"]["missing_percentage"] == pytest.approx(10.0)
    assert by_column["moderate"]["severity"] == "moderate"

    assert by_column["high"]["missing_count"] == 40
    assert by_column["high"]["missing_percentage"] == pytest.approx(40.0)
    assert by_column["high"]["severity"] == "high"


def test_fully_missing_column_reports_100_percent(simple_clean_df):
    df = simple_clean_df.assign(blank=None)

    by_column = {r["column_name"]: r for r in detect_missing_values(df)}

    assert by_column["blank"]["missing_count"] == 6
    assert by_column["blank"]["missing_percentage"] == 100.0
    assert by_column["blank"]["severity"] == "high"


def test_detects_missing_values_in_non_numeric_columns(simple_clean_df):
    df = simple_clean_df.copy()
    df.loc[0, "group"] = None

    by_column = {r["column_name"]: r for r in detect_missing_values(df)}

    assert by_column["group"]["missing_count"] == 1


def test_empty_dataframe_returns_empty_list():
    assert detect_missing_values(pd.DataFrame()) == []


@pytest.mark.parametrize(
    "percentage, expected",
    [
        (0, "none"),
        (0.1, "low"),
        (4.99, "low"),
        (5, "moderate"),
        (19.99, "moderate"),
        (20, "high"),
        (100, "high"),
    ],
)
def test_classify_severity_boundaries(percentage, expected):
    assert classify_severity(percentage) == expected
