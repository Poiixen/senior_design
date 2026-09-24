"""Reusable, dataset-agnostic CSV ingestion utilities."""

import os
import pandas as pd


class CSVLoadError(Exception):
    """Raised when a CSV file cannot be loaded."""


def load_csv(file_path: str, **options) -> pd.DataFrame:
    """Load an arbitrary CSV file into a pandas DataFrame.

    Args:
        file_path: Path to the CSV file to load.
        **options: Additional keyword arguments forwarded to pandas.read_csv
            (e.g. sep, header, dtype, encoding, usecols).

    Returns:
        The loaded DataFrame.

    Raises:
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file is not readable.
        CSVLoadError: If the file is empty or cannot be parsed.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    if not os.path.isfile(file_path):
        raise CSVLoadError(f"Path is not a file: {file_path}")

    if not os.access(file_path, os.R_OK):
        raise PermissionError(f"CSV file is not readable: {file_path}")

    try:
        df = pd.read_csv(file_path, **options)
    except pd.errors.EmptyDataError as exc:
        raise CSVLoadError(f"CSV file is empty: {file_path}") from exc
    except pd.errors.ParserError as exc:
        raise CSVLoadError(f"Failed to parse CSV file: {file_path}") from exc

    if df.empty:
        raise CSVLoadError(f"CSV file contains no data: {file_path}")

    return df

' Csv file loaded, now we check for any data issues. Quality check.'
def validate_dataset(df: pd.DataFrame) -> dict:

    warnings = []
    row_count, column_count = df.shape

    'check dataframe sturcutre and if it is supported.'
    if not isinstance(df, pd.DataFrame):

        'doesnt append, just returns warning message'
        return {

            "valid": False,
            "rows": 0,
            "columns": 0,
            "warnings": ["Input is not a pandas DataFrame"],
        }


    'DATASET'

    'empty dataset'
    if row_count == 0:

        warnings.append("Dataset is empty")

    'zero columns'
    if column_count == 0:

        warnings.append("Dataset has zero columns")

    'dupe column names'
    if df.columns.duplicated().any():

        duplicate_columns = df.columns[df.columns.duplicated()].tolist()

        warnings.append(f"Duplicate column names found: {duplicate_columns}, count: {len(duplicate_columns)}")

    'empty columns'

    if df.columns[df.isna().all()].tolist():
        empty_columns = df.columns[df.isna().all()].tolist()

        warnings.append(

            f"Completely empty columns found: {empty_columns}"
        )

 
    'extrememly smalll dataset less then 5'
    if row_count < 5:
        warnings.append("Dataset is extremely small (fewer than 5 rows)")

    return {

        "valid": len(warnings) == 0,

        "rows": row_count,

        "columns": column_count,

        "warnings": warnings,

    }

' DIGESTION CODE will be moved into digestion file'

def profile_dataset(df: pd.DataFrame) -> dict:
    'column types'
    numeric_columns = []

    categorical_columns = []

    'rest of the indo'
    column_details = []

    'diagnose column type'
    for i, column_name in enumerate(df.columns):

        column = df.iloc[:, i]

        if pd.api.types.is_numeric_dtype(column):

            inferred_category = "numeric"

            numeric_columns.append(column_name)

        else:

            inferred_category = "categorical"

            categorical_columns.append(column_name)

        'populate column details'
        column_details.append({

            "name": column_name,

            "dtype": str(column.dtype),

            "category": inferred_category,

            "unique_values": int(column.nunique(dropna=True)),

            "missing_count": int(column.isna().sum()),

        })

    return {

        "rows": len(df),

        "columns": len(df.columns),

        "numeric_columns": numeric_columns,

        "categorical_columns": categorical_columns,

        "duplicate_rows": int(df.duplicated().sum()),

        "column_details": column_details,

    }
    