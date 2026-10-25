"""Load supported tabular dataset formats into a DataFrame."""

import json
import os
from pathlib import Path

import pandas as pd

from backend.ingestion.csv_loader import CSVLoadError, load_csv

SUPPORTED_FILE_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".json"}


class DatasetLoadError(Exception):
    """A user-correctable dataset ingestion failure."""


def load_dataset(file_path: str, file_name: str, **options) -> pd.DataFrame:
    """Load a supported upload, dispatching by its original filename."""
    extension = Path(file_name).suffix.lower()
    if extension not in SUPPORTED_FILE_EXTENSIONS:
        raise DatasetLoadError("Unsupported file format. Choose a CSV, TSV, XLSX, or JSON file.")
    if not os.path.exists(file_path):
        raise DatasetLoadError("The uploaded file could not be found.")
    if not os.path.isfile(file_path) or not os.access(file_path, os.R_OK):
        raise DatasetLoadError("The uploaded file could not be read.")
    if os.path.getsize(file_path) == 0:
        raise DatasetLoadError("The uploaded file is empty.")

    try:
        if extension in {".csv", ".tsv"}:
            if extension == ".tsv":
                options["sep"] = "\t"
            return load_csv(file_path, **options)
        if extension == ".xlsx":
            frame = pd.read_excel(file_path, sheet_name=0)
        else:
            with open(file_path, encoding="utf-8") as source:
                value = json.load(source)
            if not isinstance(value, list) or not value or not all(isinstance(record, dict) for record in value):
                raise DatasetLoadError("JSON must be a non-empty array of tabular record objects.")
            if any(any(isinstance(item, (dict, list)) for item in record.values()) for record in value):
                raise DatasetLoadError("Nested JSON is not supported; use flat record objects.")
            frame = pd.DataFrame.from_records(value)
    except DatasetLoadError:
        raise
    except CSVLoadError as exc:
        raise DatasetLoadError("The CSV or TSV file could not be parsed. Check its formatting.") from exc
    except UnicodeDecodeError as exc:
        raise DatasetLoadError("The file encoding is not supported. Use UTF-8 or ASCII.") from exc
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        label = "JSON" if extension == ".json" else "Excel workbook"
        raise DatasetLoadError(f"The {label} could not be parsed.") from exc
    except (OSError, ImportError) as exc:
        label = "Excel workbook" if extension == ".xlsx" else "file"
        raise DatasetLoadError(f"The {label} could not be read.") from exc

    if frame.empty:
        raise DatasetLoadError("The uploaded file contains no data.")
    return frame
