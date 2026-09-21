"""Tests for the UCI Adult dataset adapter."""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "ingestion"))

from backend.ingestion.adult_adapter import ADULT_COLUMNS, load_adult
from backend.ingestion.csv_loader import CSVLoadError

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "UCI_ADULT_INCOME")
TRAIN_PATH = os.path.join(DATA_DIR, "adult.data")
TEST_PATH = os.path.join(DATA_DIR, "adult.test")

TRAIN_ROW = (
    "39, State-gov, 77516, Bachelors, 13, Never-married, Adm-clerical,"
    " Not-in-family, White, Male, 2174, 0, 40, United-States, <=50K\n"
)
TRAIN_ROW_WITH_MISSING = (
    "38, ?, 215646, HS-grad, 9, Divorced, ?, Not-in-family, White, Male,"
    " 0, 0, 40, ?, >50K\n"
)
TEST_ROW = (
    "25, Private, 226802, 11th, 7, Never-married, Machine-op-inspct,"
    " Own-child, Black, Male, 0, 0, 40, United-States, <=50K.\n"
)
TEST_METADATA_LINE = "|1x3 Cross validator\n"


@pytest.fixture
def train_file(tmp_path):
    path = tmp_path / "adult.data"
    path.write_text(TRAIN_ROW + TRAIN_ROW_WITH_MISSING)
    return str(path)


@pytest.fixture
def test_file(tmp_path):
    path = tmp_path / "adult.test"
    path.write_text(TEST_METADATA_LINE + TEST_ROW)
    return str(path)


def test_train_applies_standard_columns(train_file):
    df = load_adult(train_file)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ADULT_COLUMNS
    assert df.shape == (2, len(ADULT_COLUMNS))


def test_train_strips_spaces_after_commas(train_file):
    df = load_adult(train_file)
    assert df.loc[0, "workclass"] == "State-gov"
    assert df.loc[0, "native_country"] == "United-States"
    assert df.loc[0, "income"] == "<=50K"


def test_train_converts_question_marks_to_nan(train_file):
    df = load_adult(train_file)
    assert df.loc[1, ["workclass", "occupation", "native_country"]].isna().all()
    assert not df.loc[0, ["workclass", "occupation", "native_country"]].isna().any()


def test_train_parses_numeric_columns_as_numbers(train_file):
    df = load_adult(train_file)
    for column in ("age", "fnlwgt", "education_num", "capital_gain", "capital_loss", "hours_per_week"):
        assert pd.api.types.is_numeric_dtype(df[column]), column
    assert df.loc[0, "age"] == 39
    assert df.loc[0, "capital_gain"] == 2174


def test_test_skips_metadata_line(test_file):
    df = load_adult(test_file)
    assert df.shape == (1, len(ADULT_COLUMNS))
    assert df.loc[0, "age"] == 25


def test_test_strips_trailing_period_from_income(test_file):
    df = load_adult(test_file)
    assert df.loc[0, "income"] == "<=50K"


def test_test_handles_file_without_metadata_line(tmp_path):
    path = tmp_path / "adult_no_metadata.test"
    path.write_text(TEST_ROW)
    df = load_adult(str(path))
    assert df.shape == (1, len(ADULT_COLUMNS))
    assert df.loc[0, "income"] == "<=50K"


def test_train_and_test_share_schema_and_labels(train_file, test_file):
    train = load_adult(train_file)
    test = load_adult(test_file)
    assert list(train.columns) == list(test.columns)
    assert set(test["income"]).issubset({"<=50K", ">50K"})


def test_adapter_ignores_trailing_blank_lines(tmp_path):
    path = tmp_path / "adult_trailing_blank.data"
    path.write_text(TRAIN_ROW + "\n")
    df = load_adult(path.as_posix())
    assert df.shape == (1, len(ADULT_COLUMNS))


@pytest.mark.parametrize("marker", ["?", "? ", " ? ", "?\t"])
def test_padded_question_mark_is_treated_as_missing(tmp_path, marker):
    path = tmp_path / "padded.data"
    path.write_text(TRAIN_ROW.replace(" United-States,", f" {marker},"))
    df = load_adult(str(path))
    assert pd.isna(df.loc[0, "native_country"])


@pytest.mark.parametrize("marker", ["?", "? "])
def test_padded_question_mark_in_numeric_column_keeps_column_numeric(tmp_path, marker):
    path = tmp_path / "padded_numeric.data"
    path.write_text(TRAIN_ROW + TRAIN_ROW.replace("39, State-gov", f"{marker}, State-gov"))
    df = load_adult(str(path))
    assert pd.isna(df.loc[1, "age"])
    assert pd.api.types.is_numeric_dtype(df["age"])
    assert df.loc[0, "age"] == 39


def test_non_numeric_value_in_numeric_column_raises_csv_load_error(tmp_path):
    path = tmp_path / "bad_numeric.data"
    path.write_text(TRAIN_ROW.replace("39, State-gov", "unknown, State-gov"))
    with pytest.raises(CSVLoadError, match="age"):
        load_adult(str(path))


def test_test_file_with_utf8_bom_still_skips_metadata_line(tmp_path):
    path = tmp_path / "adult_bom.test"
    path.write_text(TEST_METADATA_LINE + TEST_ROW, encoding="utf-8-sig")
    df = load_adult(str(path))
    assert df.shape == (1, len(ADULT_COLUMNS))
    assert df.loc[0, "age"] == 25


def test_train_file_with_utf8_bom_parses_first_field(tmp_path):
    path = tmp_path / "adult_bom.data"
    path.write_text(TRAIN_ROW, encoding="utf-8-sig")
    df = load_adult(str(path))
    assert df.loc[0, "age"] == 39
    assert pd.api.types.is_numeric_dtype(df["age"])


def test_file_without_income_column_raises_csv_load_error(tmp_path):
    path = tmp_path / "truncated.data"
    path.write_text("25, Private, 226802\n")
    with pytest.raises(CSVLoadError, match="income"):
        load_adult(str(path))


def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_adult(str(tmp_path / "does_not_exist.data"))


def test_empty_file_raises_csv_load_error(tmp_path):
    path = tmp_path / "empty.data"
    path.write_text("")
    with pytest.raises(CSVLoadError):
        load_adult(str(path))


def test_directory_path_raises_csv_load_error(tmp_path):
    with pytest.raises(CSVLoadError, match="not a file"):
        load_adult(str(tmp_path))


def test_metadata_line_without_data_rows_raises_csv_load_error(tmp_path):
    path = tmp_path / "metadata_only.test"
    path.write_text(TEST_METADATA_LINE)
    with pytest.raises(CSVLoadError, match="metadata"):
        load_adult(str(path))


@pytest.mark.skipif(not os.path.exists(TRAIN_PATH), reason="UCI adult.data is not available")
def test_real_train_file_loads_cleanly():
    df = load_adult(TRAIN_PATH)
    assert list(df.columns) == ADULT_COLUMNS
    assert len(df) == 32561
    assert set(df["income"]) == {"<=50K", ">50K"}
    assert not df.astype(str).apply(lambda col: col.str.contains(r"^\s|\s$")).any().any()


@pytest.mark.skipif(not os.path.exists(TEST_PATH), reason="UCI adult.test is not available")
def test_real_test_file_loads_cleanly():
    df = load_adult(TEST_PATH)
    assert list(df.columns) == ADULT_COLUMNS
    assert len(df) == 16281
    assert set(df["income"]) == {"<=50K", ">50K"}
    assert pd.api.types.is_numeric_dtype(df["age"])
