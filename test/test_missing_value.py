"""Tests for missing value detection."""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "diagnostics"))

from backend.diagnostics.missing_value_detection import detect_missing_values
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
def no_missing_df():
    return pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})


@pytest.fixture
def some_missing_df():
    return pd.DataFrame({"a": [1, None, 3], "b": [4, 5, None]})


@pytest.fixture
def all_missing_column_df():
    return pd.DataFrame({"a": [1, 2, 3], "b": [None, None, None]})


def test_detect_missing_values_returns_empty_list_when_no_missing_values(no_missing_df):
    result = detect_missing_values(no_missing_df)
    assert result == []


def test_detect_missing_values_reports_count_and_percentage(some_missing_df):
    result = detect_missing_values(some_missing_df)
    result_by_column = {row["column_name"]: row for row in result}

    assert result_by_column["a"]["missing_count"] == 1
    assert result_by_column["a"]["missing_percentage"] == pytest.approx(33.333333, rel=1e-3)
    assert result_by_column["b"]["missing_count"] == 1
    assert result_by_column["b"]["missing_percentage"] == pytest.approx(33.333333, rel=1e-3)


def test_detect_missing_values_reports_fully_missing_column(all_missing_column_df):
    result = detect_missing_values(all_missing_column_df)
    result_by_column = {row["column_name"]: row for row in result}

    assert "a" not in result_by_column
    assert result_by_column["b"]["missing_count"] == 3
    assert result_by_column["b"]["missing_percentage"] == 100.0


def test_detect_missing_values_classifies_severity_by_percentage():
    rows = 100
    df = pd.DataFrame({
        "low_col": [None] * 3 + [1] * (rows - 3),
        "moderate_col": [None] * 10 + [1] * (rows - 10),
        "high_col": [None] * 25 + [1] * (rows - 25),
    })
    print(df)
    result = detect_missing_values(df)
    result_by_column = {row["column_name"]: row for row in result}

    assert result_by_column["low_col"]["severity"] == "low"
    assert result_by_column["moderate_col"]["severity"] == "moderate"
    assert result_by_column["high_col"]["severity"] == "high"


def test_detect_missing_values_on_adult_dataset():
    df = load_csv(
        ADULT_DATA_PATH,
        header=None,
        names=ADULT_COLUMNS,
        na_values="?",
        skipinitialspace=True,
    )

    result = detect_missing_values(df)
    result_by_column = {row["column_name"]: row for row in result}

    assert result_by_column["workclass"]["missing_count"] == 1836
    assert result_by_column["workclass"]["severity"] == "moderate"

    assert result_by_column["occupation"]["missing_count"] == 1843
    assert result_by_column["occupation"]["severity"] == "moderate"

    assert result_by_column["native_country"]["missing_count"] == 583
    assert result_by_column["native_country"]["severity"] == "low"
