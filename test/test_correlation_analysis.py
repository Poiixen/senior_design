"""Tests for numeric correlation analysis."""

import json

import numpy as np
import pandas as pd
import pytest

from backend.diagnostics.correlation_analysis import calculate_correlation_matrix
from backend.diagnostics.generic_dataset_analysis_pipeline import analyze_dataset


def test_perfect_positive_correlation():
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": [2, 4, 6, 8]})

    result = calculate_correlation_matrix(df)

    assert result["matrix"][0][1] == pytest.approx(1.0)
    assert result["matrix"][1][0] == pytest.approx(1.0)


def test_perfect_negative_correlation():
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": [8, 6, 4, 2]})

    result = calculate_correlation_matrix(df)

    assert result["matrix"][0][1] == pytest.approx(-1.0)


def test_near_zero_relationship():
    df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [2, 4, 1, 5, 3]})

    result = calculate_correlation_matrix(df)

    assert abs(result["matrix"][0][1]) < 0.5


def test_multiple_numeric_columns_form_square_matrix():
    df = pd.DataFrame({
        "age": [20, 30, 40, 50],
        "income": [10, 20, 35, 40],
        "score": [5, 3, 4, 1],
    })

    result = calculate_correlation_matrix(df)

    assert len(result["matrix"]) == 3
    assert all(len(row) == 3 for row in result["matrix"])
    for i in range(3):
        assert result["matrix"][i][i] == pytest.approx(1.0)
        for j in range(3):
            assert result["matrix"][i][j] == pytest.approx(result["matrix"][j][i])
            assert -1.0 <= result["matrix"][i][j] <= 1.0


def test_missing_values_are_dropped_pairwise():
    df = pd.DataFrame({
        "a": [1, 2, 3, 4, np.nan],
        "b": [2, 4, 6, 8, 100],
    })

    result = calculate_correlation_matrix(df)

    assert result["matrix"][0][1] == pytest.approx(1.0)


def test_constant_column_gives_none():
    df = pd.DataFrame({"a": [1, 2, 3], "const": [5, 5, 5]})

    result = calculate_correlation_matrix(df)

    assert result["matrix"][0][1] is None
    assert result["matrix"][1][0] is None
    assert result["matrix"][1][1] is None
    assert result["matrix"][0][0] == pytest.approx(1.0)
    json.dumps(result, allow_nan=False)


def test_one_numeric_column():
    df = pd.DataFrame({"a": [1, 2, 3], "label": ["x", "y", "z"]})

    result = calculate_correlation_matrix(df)

    assert result["columns"] == ["a"]
    assert result["matrix"] == [[1.0]]


def test_no_numeric_columns():
    df = pd.DataFrame({"label": ["x", "y"], "other": ["p", "q"]})

    assert calculate_correlation_matrix(df) == {"columns": [], "matrix": []}


def test_empty_dataframe():
    assert calculate_correlation_matrix(pd.DataFrame()) == {"columns": [], "matrix": []}


def test_empty_numeric_column_gives_none():
    df = pd.DataFrame({"a": pd.Series([], dtype="float64")})

    result = calculate_correlation_matrix(df)

    assert result["columns"] == ["a"]
    assert result["matrix"] == [[None]]


def test_infinite_values_are_json_safe():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [1, np.inf, 3]})

    result = calculate_correlation_matrix(df)

    json.dumps(result, allow_nan=False)


def test_boolean_columns_are_treated_as_numeric():
    df = pd.DataFrame({"flag": [True, False, True, False], "n": [1, 0, 1, 0]})

    result = calculate_correlation_matrix(df)

    assert result["columns"] == ["flag", "n"]
    assert result["matrix"][0][1] == pytest.approx(1.0)


def test_matrix_order_matches_column_order():
    df = pd.DataFrame({
        "z": [1, 2, 3, 4],
        "label": list("abcd"),
        "a": [4, 3, 2, 1],
        "m": [1, 2, 3, 5],
    })

    result = calculate_correlation_matrix(df)

    assert result["columns"] == ["z", "a", "m"]
    assert result["matrix"][0][1] == pytest.approx(-1.0)
    assert result["matrix"][1][0] == pytest.approx(-1.0)
    assert result["matrix"][0][2] > 0.9


def test_pipeline_exposes_correlation(simple_clean_df):
    result = analyze_dataset(simple_clean_df)

    correlation = next(
        item["results"] for item in result["diagnostics"] if item["type"] == "correlation"
    )
    assert correlation["columns"] == ["id", "score"]
