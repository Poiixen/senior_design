"""Tests for duplicate row detection."""

import os

import pandas as pd
import pytest

from backend.diagnostics.duplicate_detection import detect_duplicates
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
def no_duplicates_df():
    return pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})


@pytest.fixture
def some_duplicates_df():
    return pd.DataFrame({"a": [1, 1, 2, 3], "b": [4, 4, 5, 6]})


@pytest.fixture
def all_duplicates_df():
    return pd.DataFrame({"a": [1, 1, 1], "b": [4, 4, 4]})


def test_detect_duplicates_returns_zero_when_no_duplicates(no_duplicates_df):
    result = detect_duplicates(no_duplicates_df)

    assert result["duplicate_count"] == 0
    assert result["duplicate_percentage"] == 0.0


def test_detect_duplicates_reports_count_and_percentage(some_duplicates_df):
    result = detect_duplicates(some_duplicates_df)

    assert result["duplicate_count"] == 1
    assert result["duplicate_percentage"] == pytest.approx(25.0)


def test_detect_duplicates_reports_all_rows_duplicated(all_duplicates_df):
    result = detect_duplicates(all_duplicates_df)

    assert result["duplicate_count"] == 2
    assert result["duplicate_percentage"] == pytest.approx(66.666666, rel=1e-3)


def test_detect_duplicates_on_adult_dataset():
    df = load_csv(
        ADULT_DATA_PATH,
        header=None,
        names=ADULT_COLUMNS,
        na_values="?",
        skipinitialspace=True,
    )

    result = detect_duplicates(df)

    assert result["duplicate_count"] == 24
    assert result["duplicate_percentage"] == pytest.approx(0.0737, rel=1e-2)
