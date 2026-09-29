"""Tests for the generic dataset analysis pipeline."""

import pandas as pd

from backend.diagnostics.generic_dataset_analysis_pipeline import analyze_dataset


def test_clean_dataset_returns_profile_and_diagnostics(simple_clean_df):
    result = analyze_dataset(simple_clean_df)

    assert "profile" in result
    assert "diagnostics" in result


def test_clean_dataset_profile_is_correct(simple_clean_df):
    result = analyze_dataset(simple_clean_df)

    assert result["profile"]["rows"] == 6
    assert result["profile"]["columns"] == 3


def test_numeric_and_categorical_columns_are_profiled(simple_clean_df):
    result = analyze_dataset(simple_clean_df)

    assert len(result["profile"]["numeric_columns"]) > 0
    assert len(result["profile"]["categorical_columns"]) > 0


def test_missing_values_are_detected(missing_values_df):
    result = analyze_dataset(missing_values_df)

    missing_results = next(
        item["results"]
        for item in result["diagnostics"]
        if item["type"] == "missing_values"
    )

    assert len(missing_results) > 0


def test_duplicates_are_detected():
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Bob", "Cara", "Dan"],
        "age": [20, 21, 21, 22, 23],
    })

    result = analyze_dataset(df)

    duplicate_results = next(
        item["results"]
        for item in result["diagnostics"]
        if item["type"] == "duplicates"
    )

    assert duplicate_results["duplicate_count"] == 1


def test_outliers_are_detected():
    df = pd.DataFrame({
        "age": [20, 21, 22, 23, 100],
    })

    result = analyze_dataset(df)

    outlier_results = next(
        item["results"]
        for item in result["diagnostics"]
        if item["type"] == "outliers"
    )

    assert outlier_results[0]["column_name"] == "age"
    assert outlier_results[0]["outlier_count"] == 1


def test_non_dataframe_input_returns_empty_results():
    result = analyze_dataset(["Alice", "Bob", "Cara"])

    assert result["profile"] == {}
    assert result["diagnostics"] == []