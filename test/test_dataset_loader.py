import json

import pandas as pd
import pytest

from backend.ingestion.dataset_loader import DatasetLoadError, load_dataset


def test_loads_csv_with_existing_options(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("Alice;10\nmissing;20\n", encoding="utf-8")
    result = load_dataset(str(path), path.name, sep=";", header=None, na_values=["missing"])
    assert result.shape == (2, 2)
    assert pd.isna(result.iloc[1, 0])


def test_loads_tsv_with_tab_delimiter(tmp_path):
    path = tmp_path / "data.tsv"
    path.write_text("name\tage\nAlice\t20\n", encoding="utf-8")
    assert load_dataset(str(path), path.name).to_dict("records") == [{"name": "Alice", "age": 20}]


def test_loads_first_xlsx_worksheet(tmp_path):
    path = tmp_path / "data.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"name": ["Alice"], "age": [20]}).to_excel(writer, index=False, sheet_name="first")
        pd.DataFrame({"ignored": [True]}).to_excel(writer, index=False, sheet_name="second")
    assert list(load_dataset(str(path), path.name).columns) == ["name", "age"]


def test_loads_json_records(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps([{"name": "Alice", "age": 20}]), encoding="utf-8")
    assert load_dataset(str(path), path.name).to_dict("records") == [{"name": "Alice", "age": 20}]


@pytest.mark.parametrize("name,contents", [("data.json", "not json"), ("data.xlsx", b"not excel")])
def test_rejects_invalid_supported_files(tmp_path, name, contents):
    path = tmp_path / name
    path.write_bytes(contents if isinstance(contents, bytes) else contents.encode())
    with pytest.raises(DatasetLoadError):
        load_dataset(str(path), path.name)


def test_rejects_nested_json_and_unsupported_extensions(tmp_path):
    nested = tmp_path / "nested.json"
    nested.write_text('[{"person": {"name": "Alice"}}]', encoding="utf-8")
    with pytest.raises(DatasetLoadError, match="Nested JSON"):
        load_dataset(str(nested), nested.name)
    with pytest.raises(DatasetLoadError, match="Unsupported"):
        load_dataset(str(nested), "data.txt")
