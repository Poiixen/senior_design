"""Tests for duplicate row detection."""

import pandas as pd
import pytest

from backend.diagnostics.duplicate_detection import detect_duplicates


def test_no_duplicates_reports_zero(simple_clean_df):
    result = detect_duplicates(simple_clean_df)

    assert result["duplicate_count"] == 0
    assert result["duplicate_percentage"] == 0.0


def test_reports_count_and_percentage(duplicate_rows_df):
    result = detect_duplicates(duplicate_rows_df)

    assert result["duplicate_count"] == 2
    assert result["duplicate_percentage"] == pytest.approx(25.0)


def test_only_repeat_occurrences_are_counted():
    # 3 identical rows = 1 original + 2 duplicates.
    df = pd.DataFrame({"a": [1, 1, 1], "b": [4, 4, 4]})

    result = detect_duplicates(df)

    assert result["duplicate_count"] == 2
    assert result["duplicate_percentage"] == pytest.approx(66.666666, rel=1e-3)


def test_rows_differing_in_one_column_are_not_duplicates():
    df = pd.DataFrame({"a": [1, 1], "b": ["x", "y"]})

    assert detect_duplicates(df)["duplicate_count"] == 0


def test_empty_dataframe_avoids_division_by_zero():
    result = detect_duplicates(pd.DataFrame({"a": []}))

    assert result["duplicate_count"] == 0
    assert result["duplicate_percentage"] == 0.0


def test_missing_values_compare_as_equal():
    df = pd.DataFrame({"a": [None, None], "b": [1, 1]})

    assert detect_duplicates(df)["duplicate_count"] == 1
