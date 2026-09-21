"""Tests for the reusable CSV ingestion loader."""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "ingestion"))

from backend.ingestion.csv_loader import (
    CSVLoadError,
    load_csv,
    validate_dataset,
    profile_dataset
)


@pytest.fixture
def valid_csv(tmp_path):
    path = tmp_path / "valid.csv"
    path.write_text("a,b,c\n1,2,3\n4,5,6\n")
    return str(path)


@pytest.fixture
def empty_csv(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("")
    return str(path)


@pytest.fixture
def header_only_csv(tmp_path):
    path = tmp_path / "header_only.csv"
    path.write_text("a,b,c\n")
    return str(path)


@pytest.fixture
def malformed_csv(tmp_path):
    path = tmp_path / "malformed.csv"
    path.write_text('a,b,c\n1,2\n"3,4,5,6\n')
    return str(path)


def test_load_csv_returns_dataframe(valid_csv):
    df = load_csv(valid_csv)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["a", "b", "c"]
    assert df.shape == (2, 3)


def test_load_csv_missing_file_raises_file_not_found(tmp_path):
    missing_path = str(tmp_path / "does_not_exist.csv")
    with pytest.raises(FileNotFoundError):
        load_csv(missing_path)


def test_load_csv_directory_path_raises_csv_load_error(tmp_path):
    with pytest.raises(CSVLoadError):
        load_csv(str(tmp_path))


def test_load_csv_empty_file_raises_csv_load_error(empty_csv):
    with pytest.raises(CSVLoadError):
        load_csv(empty_csv)


def test_load_csv_header_only_file_raises_csv_load_error(header_only_csv):
    with pytest.raises(CSVLoadError):
        load_csv(header_only_csv)


def test_load_csv_malformed_file_raises_csv_load_error(malformed_csv):
    with pytest.raises(CSVLoadError):
        load_csv(malformed_csv, sep=",", engine="python")


def test_load_csv_forwards_pandas_options(tmp_path):
    path = tmp_path / "semicolon.csv"
    path.write_text("a;b;c\n1;2;3\n")
    df = load_csv(str(path), sep=";")
    assert list(df.columns) == ["a", "b", "c"]
    assert df.shape == (1, 3)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not enforced on Windows")
def test_load_csv_unreadable_file_raises_permission_error(valid_csv):
    os.chmod(valid_csv, 0o000)
    try:
        with pytest.raises(PermissionError):
            load_csv(valid_csv)
    finally:
        os.chmod(valid_csv, 0o644)


" -----Validate data set tests"
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

" ------Data details test"

# Profile dataset tests

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
    assert result["duplicate_rows"] == 0


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
        "missing_count": 0,
    }

    assert result["column_details"][1] == {
        "name": "age",
        "dtype": "float64",
        "category": "numeric",
        "unique_values": 3,
        "missing_count": 1,
    }


def test_profile_dataset_counts_duplicate_rows():
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Alice", "Alice"],
        "age": [20, 21, 20, 20],
    })

    result = profile_dataset(df)

    assert result["duplicate_rows"] == 2


def test_profile_dataset_counts_unique_values_and_missing_values():
    df = pd.DataFrame({
        "name": ["Alice", "Bob", "Alice", None, "Bob"],
        "score": [10, 20, 10, 30, None],
    })

    result = profile_dataset(df)

    name_details = result["column_details"][0]
    score_details = result["column_details"][1]

    assert name_details["unique_values"] == 2
    assert name_details["missing_count"] == 1

    assert score_details["unique_values"] == 3
    assert score_details["missing_count"] == 1