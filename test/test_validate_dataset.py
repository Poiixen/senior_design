import os
import sys

import pandas as pd

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "backend", "diagnostics")
)

from backend.diagnostics.validate_dataset import validate_dataset

def test_validate_normal_dataset():
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
        "age": [20, 21, 22, 23, 24],
    })

    result = validate_dataset(df)

    assert result["valid"] is True
    assert result["rows"] == 5
    assert result["columns"] == 2
    assert result["warnings"] == []


def test_validate_empty_dataset():
    df = pd.DataFrame()

    result = validate_dataset(df)

    assert result["valid"] is False
    assert "Dataset is empty" in result["warnings"]
    assert "Dataset has zero columns" in result["warnings"]


def test_validate_duplicate_columns():
    df = pd.DataFrame(
        [
            ["Alice", 20, "NY"],
            ["Bob", 21, "FL"],
            ["Charlie", 22, "TX"],
            ["David", 23, "CA"],
            ["Eve", 24, "MA"],
        ],
        columns=["name", "age", "name"],
    )

    result = validate_dataset(df)

    assert result["valid"] is False
    assert "Duplicate column names found: ['name'], count: 1" in result["warnings"]


def test_validate_empty_column():
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
        "empty_column": [None, None, None, None, None],
    })

    result = validate_dataset(df)

    assert result["valid"] is False
    assert "Completely empty columns found: ['empty_column']" in result["warnings"]


def test_validate_small_dataset():
    df = pd.DataFrame({
        "name": ["Alice", "Bob"],
        "age": [20, 21],
    })

    result = validate_dataset(df)

    assert result["valid"] is False
    assert "Dataset is extremely small (fewer than 5 rows)" in result["warnings"]