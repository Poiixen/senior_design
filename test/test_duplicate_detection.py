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


def test_new_fields_are_zeroed_without_duplicates(simple_clean_df):
    result = detect_duplicates(simple_clean_df)

    assert result["duplicate_group_count"] == 0
    assert result["rows_in_duplicate_groups"] == 0
    assert result["largest_duplicate_group_size"] == 0
    assert result["duplicate_columns"] == []
    assert result["repeated_value_summary"] == []


def test_one_duplicate_pair():
    df = pd.DataFrame({"name": ["Alice", "Alice", "Bob"], "age": [20, 20, 30]})

    result = detect_duplicates(df)

    assert result["duplicate_count"] == 1
    assert result["duplicate_group_count"] == 1
    assert result["rows_in_duplicate_groups"] == 2
    assert result["largest_duplicate_group_size"] == 2


def test_three_identical_rows_form_one_group():
    df = pd.DataFrame({"name": ["Alice"] * 3, "age": [20] * 3})

    result = detect_duplicates(df)

    assert result["duplicate_count"] == 2
    assert result["duplicate_group_count"] == 1
    assert result["rows_in_duplicate_groups"] == 3
    assert result["largest_duplicate_group_size"] == 3


def test_multiple_duplicate_groups(duplicate_rows_df):
    df = pd.concat([duplicate_rows_df, duplicate_rows_df.iloc[[0]]], ignore_index=True)

    result = detect_duplicates(df)

    assert result["duplicate_count"] == 3
    assert result["duplicate_group_count"] == 2
    assert result["rows_in_duplicate_groups"] == 5
    assert result["largest_duplicate_group_size"] == 3


def test_duplicate_rows_with_missing_values_are_grouped():
    df = pd.DataFrame({
        "a": [None, None, None, 1.0],
        "b": ["x", "x", "y", "y"],
    })

    result = detect_duplicates(df)

    assert result["duplicate_count"] == 1
    assert result["duplicate_group_count"] == 1
    assert result["rows_in_duplicate_groups"] == 2
    assert result["largest_duplicate_group_size"] == 2


def test_empty_dataframe_new_fields_are_safe():
    for df in (pd.DataFrame(), pd.DataFrame({"a": []})):
        result = detect_duplicates(df)

        assert result["duplicate_group_count"] == 0
        assert result["rows_in_duplicate_groups"] == 0
        assert result["largest_duplicate_group_size"] == 0
        assert result["duplicate_columns"] == []
        assert result["repeated_value_summary"] == []


def test_repeated_values_reported_for_identifier_like_columns():
    # email repeats across otherwise different records; country is
    # low-cardinality so its repetition is expected and not reported.
    df = pd.DataFrame({
        "email": ["a@x.com", "a@x.com", "a@x.com", "b@x.com", "c@x.com", "d@x.com"],
        "country": ["US", "US", "CA", "US", "CA", "US"],
        "order_id": [1, 2, 3, 4, 5, 6],
    })

    result = detect_duplicates(df)

    assert result["duplicate_count"] == 0
    assert result["duplicate_columns"] == ["email"]
    assert result["repeated_value_summary"] == [
        {"column_name": "email", "repeated_values": 1, "rows_affected": 3}
    ]


def test_exact_duplicates_do_not_hide_identifier_columns():
    df = pd.DataFrame({"name": ["Alice"] * 3, "age": [20] * 3})

    result = detect_duplicates(df)

    assert sorted(result["duplicate_columns"]) == ["age", "name"]
    for entry in result["repeated_value_summary"]:
        assert entry["repeated_values"] == 1
        assert entry["rows_affected"] == 3


def test_missing_values_are_not_counted_as_repeated_values():
    df = pd.DataFrame({"email": ["a@x.com", None, None, "b@x.com"]})

    result = detect_duplicates(df)

    assert result["duplicate_columns"] == []
    assert result["repeated_value_summary"] == []


def test_summary_contains_no_raw_values():
    df = pd.DataFrame({"email": ["secret@x.com", "secret@x.com", "b@x.com"]})

    result = detect_duplicates(df)

    assert "secret@x.com" not in repr(result)
    assert set(result["repeated_value_summary"][0]) == {
        "column_name", "repeated_values", "rows_affected"
    }
