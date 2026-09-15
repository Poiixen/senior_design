"""Tests for the reusable CSV ingestion loader."""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "ingestion"))

from backend.ingestion.csv_loader import CSVLoadError, load_csv


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
