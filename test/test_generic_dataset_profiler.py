import os
import sys

import pandas as pd

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "backend", "diagnostics")
)

from backend.diagnostics.generic_dataset_profiler import profile_dataset

def test_profile_dataset_returns_basic_structure():
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
        "age": [20, 21, 22, 23, 24],
    })

    result = profile_dataset(df)

    assert result["rows"] == 5
    assert result["columns"] == 2
    assert result["numeric_columns"] == ["age"]
    assert result["categorical_columns"] == ["name"]

    assert result["duplicates"]["duplicate_count"] == 0
    assert result["duplicates"]["duplicate_percentage"] == 0.0

    assert result["missing_values"] == []


def test_profile_dataset_column_details():
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Alice", "David", "Eve"],
        "age": [20, 21, 20, None, 24],
    })

    result = profile_dataset(df)

    assert result["column_details"][0] == {
        "name": "name",
        "dtype": "object",
        "category": "categorical",
        "unique_values": 4,
    }

    assert result["column_details"][1] == {
        "name": "age",
        "dtype": "float64",
        "category": "numeric",
        "unique_values": 3,
    }


def test_profile_dataset_counts_duplicate_rows():
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Alice", "Alice"],
        "age": [20, 21, 20, 20],
    })

    result = profile_dataset(df)

    assert result["duplicates"]["duplicate_count"] == 2
    assert result["duplicates"]["duplicate_percentage"] == 50.0


def test_profile_dataset_counts_unique_values_and_missing_values():
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Alice", None, "Bob"],
        "score": [10, 20, 10, 30, None],
    })

    result = profile_dataset(df)

    name_details = result["column_details"][0]
    score_details = result["column_details"][1]

    assert name_details["unique_values"] == 2
    assert score_details["unique_values"] == 3

    assert result["missing_values"] == [
        {
            "column_name": "name",
            "missing_count": 1,
            "missing_percentage": 20.0,
            "severity": "high",
        },
        {
            "column_name": "score",
            "missing_count": 1,
            "missing_percentage": 20.0,
            "severity": "high",
        },
    ]