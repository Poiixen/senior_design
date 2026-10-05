"""Shared fixtures for the test suite.

Generic fixtures are dataset-agnostic and carry hand-checked numbers so
unit tests can assert exact values. Adult fixtures are for integration
tests only and skip when the raw data is not checked out.
"""

import atexit
import os
import shutil
import tempfile

import pandas as pd
import pytest

# backend.api.main builds its SQLite engine at import time from DATABASE_PATH,
# defaulting to data/analysis.sqlite3 inside the repository. Point it at a
# throwaway directory before any test module imports the app, so running the
# suite never creates or mutates a database in the working tree. setdefault
# keeps an explicit DATABASE_PATH (CI sets one) authoritative.
_API_DATABASE_DIR = tempfile.mkdtemp(prefix="team-science-test-db-")
os.environ.setdefault(
    "DATABASE_PATH", os.path.join(_API_DATABASE_DIR, "analysis.sqlite3")
)
atexit.register(shutil.rmtree, _API_DATABASE_DIR, ignore_errors=True)

from backend.ingestion.adult_adapter import load_adult  # noqa: E402

DATA_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "raw", "UCI_ADULT_INCOME")
)
ADULT_TRAIN_PATH = os.path.join(DATA_DIR, "adult.data")
ADULT_TEST_PATH = os.path.join(DATA_DIR, "adult.test")


# --- Generic fixtures -------------------------------------------------


@pytest.fixture
def simple_clean_df():
    """6 rows, no missing/duplicate/outlier values. 2 numeric, 1 categorical."""
    return pd.DataFrame({
        "id": [1, 2, 3, 4, 5, 6],
        "score": [10.0, 12.0, 11.0, 13.0, 10.5, 12.5],
        "group": ["a", "b", "a", "c", "b", "c"],
    })


@pytest.fixture
def missing_values_df():
    """100 rows; missing at 0%, 3% (low), 10% (moderate), 40% (high)."""
    rows = 100
    return pd.DataFrame({
        "complete": list(range(rows)),
        "low": [None] * 3 + list(range(rows - 3)),
        "moderate": [None] * 10 + list(range(rows - 10)),
        "high": [None] * 40 + list(range(rows - 40)),
    })


@pytest.fixture
def duplicate_rows_df():
    """8 rows; (1,x) and (3,z) each appear twice = 25%."""
    return pd.DataFrame({
        "a": [1, 1, 2, 3, 3, 4, 5, 6],
        "b": ["x", "x", "y", "z", "z", "w", "v", "u"],
    })


@pytest.fixture
def numeric_outliers_df():
    """'value' has bounds -5.0..15.0 and 2 outliers; 'clean' has none."""
    return pd.DataFrame({
        "value": [-100] + list(range(1, 10)) + [100],
        "clean": list(range(1, 12)),
        "label": ["x"] * 11,
    })


@pytest.fixture
def mixed_types_df():
    """One column per dtype family the profiler has to classify."""
    return pd.DataFrame({
        "int_col": [1, 2, 3, 4, 5],
        "float_col": [1.5, 2.5, 3.5, 4.5, 5.5],
        "bool_col": [True, False, True, False, True],
        "str_col": ["a", "b", "c", "d", "e"],
        "date_col": pd.to_datetime(["2024-01-01"] * 5),
    })


# --- Adult_dataset hard-coded fixtures ---------------------------------------


@pytest.fixture(scope="session")
def adult_df():
    """Real adult.data through the adapter. Session-scoped: 32k rows."""
    if not os.path.exists(ADULT_TRAIN_PATH):
        pytest.skip(f"UCI Adult dataset not available: {ADULT_TRAIN_PATH}")
    return load_adult(ADULT_TRAIN_PATH)


@pytest.fixture(scope="session")
def adult_test_df():
    """Real adult.test through the adapter."""
    if not os.path.exists(ADULT_TEST_PATH):
        pytest.skip(f"UCI Adult dataset not available: {ADULT_TEST_PATH}")
    return load_adult(ADULT_TEST_PATH)
