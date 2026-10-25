"""Tests for column quality detection."""

import pandas as pd
import pytest

from backend.diagnostics.column_quality_detection import (
    NEAR_CONSTANT_THRESHOLD,
    detect_column_quality,
)

RESULT_KEYS = {
    "diagnostic",
    "column",
    "severity",
    "value",
    "message",
    "recommendation",
    "metadata",
}


def _issues(findings, column):
    return [f["metadata"]["issue"] for f in findings if f["column"] == column]


def _finding(findings, column, issue):
    return next(
        f
        for f in findings
        if f["column"] == column and f["metadata"]["issue"] == issue
    )


def _dominant(dominant_count, other_count):
    return ["Active"] * dominant_count + [f"other_{i}" for i in range(other_count)]


# --- Constant columns -------------------------------------------------


def test_constant_numeric_column_is_flagged():
    df = pd.DataFrame({"rate": [5, 5, 5, 5], "id": [1, 2, 3, 4]})

    findings = detect_column_quality(df)

    finding = _finding(findings, "rate", "constant")
    assert finding["value"] == 100.0
    assert finding["metadata"]["dominant_value_percentage"] == 100.0
    assert _issues(findings, "id") == []


def test_constant_categorical_column_is_flagged():
    df = pd.DataFrame({"country": ["USA", "USA", "USA", "USA"]})

    findings = detect_column_quality(df)

    assert findings == [
        {
            "diagnostic": "column_quality",
            "column": "country",
            "severity": "warning",
            "value": 100.0,
            "message": "Column 'country' contains only one distinct non-null value.",
            "recommendation": "Review whether this column provides useful information.",
            "metadata": {
                "issue": "constant",
                "dominant_value": "USA",
                "dominant_value_percentage": 100.0,
            },
        }
    ]


def test_constant_column_is_not_also_near_constant():
    df = pd.DataFrame({"country": ["USA"] * 30})

    assert _issues(detect_column_quality(df), "country") == ["constant"]


# --- Near-constant columns --------------------------------------------


def test_near_constant_column_is_flagged():
    df = pd.DataFrame({"status": _dominant(39, 1)})

    finding = _finding(detect_column_quality(df), "status", "near_constant")

    assert finding["severity"] == "warning"
    assert finding["value"] == pytest.approx(97.5)
    assert finding["metadata"]["dominant_value"] == "Active"
    assert finding["metadata"]["dominant_count"] == 39
    assert finding["metadata"]["dominant_value_percentage"] == pytest.approx(97.5)
    assert finding["recommendation"]


def test_column_exactly_at_threshold_is_flagged():
    assert NEAR_CONSTANT_THRESHOLD == 0.95
    df = pd.DataFrame({"status": _dominant(19, 1)})

    finding = _finding(detect_column_quality(df), "status", "near_constant")

    assert finding["value"] == pytest.approx(95.0)


def test_column_below_threshold_is_not_flagged():
    df = pd.DataFrame({"status": _dominant(18, 2)})

    assert _issues(detect_column_quality(df), "status") == []


def test_missing_values_ignored_when_finding_dominant_value():
    # 19 of 20 non-null values are "Active" (95%); counting the nulls
    # would drop the share to 19/30 and hide the issue.
    df = pd.DataFrame({"status": _dominant(19, 1) + [None] * 10})

    finding = _finding(detect_column_quality(df), "status", "near_constant")

    assert finding["value"] == pytest.approx(95.0)


def test_missing_values_do_not_count_as_a_distinct_value():
    df = pd.DataFrame({"country": ["USA", None, "USA", None, "USA"]})

    assert _issues(detect_column_quality(df), "country") == ["constant"]


# --- Numeric-like columns ---------------------------------------------


def test_mostly_numeric_strings_with_one_invalid_value():
    df = pd.DataFrame({"salary": ["50000", "52000", "unknown", "48000"]})

    finding = _finding(detect_column_quality(df), "salary", "mixed_numeric")

    assert finding["value"] == 25.0
    assert finding["message"] == (
        "1 value in 'salary' does not match the dominant numeric pattern."
    )
    assert finding["recommendation"] == (
        "Review inconsistent values before numerical analysis."
    )
    assert finding["metadata"]["inconsistent_count"] == 1
    assert finding["metadata"]["inconsistent_percentage"] == 25.0
    assert finding["metadata"]["example_values"] == ["unknown"]


def test_fully_numeric_strings_are_not_flagged():
    df = pd.DataFrame({"salary": ["50000", "52000", "51000", "48000"]})

    assert _issues(detect_column_quality(df), "salary") == []


def test_mostly_text_column_with_some_numbers_is_not_flagged():
    df = pd.DataFrame({"code": ["A", "B", "C", "1", "2"]})

    assert _issues(detect_column_quality(df), "code") == []


def test_numeric_check_does_not_modify_dataframe():
    df = pd.DataFrame({"salary": ["50000", "52000", "unknown", "48000"]})
    original = df.copy()

    detect_column_quality(df)

    pd.testing.assert_frame_equal(df, original)


# --- Date-like columns ------------------------------------------------


def test_mostly_dates_with_one_invalid_value():
    dates = [f"2024-01-{day:02d}" for day in range(1, 10)]
    df = pd.DataFrame({"signup": dates + ["not a date"]})

    finding = _finding(detect_column_quality(df), "signup", "mixed_date")

    assert finding["value"] == pytest.approx(10.0)
    assert finding["metadata"]["inconsistent_count"] == 1
    assert finding["metadata"]["example_values"] == ["not a date"]


def test_impossible_date_counts_as_inconsistent():
    dates = [f"01/{day:02d}/2024" for day in range(1, 10)]
    df = pd.DataFrame({"signup": dates + ["13/45/2024"]})

    finding = _finding(detect_column_quality(df), "signup", "mixed_date")

    assert finding["metadata"]["example_values"] == ["13/45/2024"]


def test_fully_valid_date_strings_are_not_flagged():
    df = pd.DataFrame({"signup": [f"2024-02-{day:02d}" for day in range(1, 11)]})

    assert _issues(detect_column_quality(df), "signup") == []


def test_mixed_date_formats_and_timezones_are_all_dates():
    df = pd.DataFrame({
        "signup": [
            "2024-01-01",
            "01/02/2024",
            "2024-01-03T10:00:00Z",
            "2024-01-04T10:00:00+05:00",
            "2024-01-05 10:00 PM",
            "not a date",
        ],
    })

    finding = _finding(detect_column_quality(df), "signup", "mixed_date")

    assert finding["metadata"]["example_values"] == ["not a date"]


def test_words_that_could_parse_as_dates_are_not_flagged():
    df = pd.DataFrame({"month": ["May", "June", "March", "today", "now", "other"]})

    assert _issues(detect_column_quality(df), "month") == []


# --- Columns that should not be flagged -------------------------------


def test_normal_categorical_column_is_not_flagged():
    df = pd.DataFrame({
        "city": ["Austin", "Boston", "Chicago", "Denver", "Austin", "Boston"],
    })

    assert detect_column_quality(df) == []


def test_clean_dataset_has_no_findings(simple_clean_df):
    assert detect_column_quality(simple_clean_df) == []


def test_all_null_column_is_not_flagged():
    df = pd.DataFrame({"empty": [None, None, None, None]})

    assert detect_column_quality(df) == []


def test_empty_dataframe_returns_no_findings():
    assert detect_column_quality(pd.DataFrame()) == []


def test_duplicate_column_names_are_checked_separately():
    df = pd.DataFrame([["USA", 1], ["USA", 2], ["USA", 3]], columns=["x", "x"])

    findings = detect_column_quality(df)

    assert [(f["column"], f["metadata"]["issue"]) for f in findings] == [
        ("x", "constant")
    ]


def test_findings_use_standard_result_format():
    df = pd.DataFrame({
        "country": ["USA"] * 4,
        "salary": ["50000", "52000", "unknown", "48000"],
    })

    findings = detect_column_quality(df)

    assert len(findings) == 2
    for finding in findings:
        assert set(finding) == RESULT_KEYS
        assert finding["diagnostic"] == "column_quality"
        assert isinstance(finding["value"], float)
