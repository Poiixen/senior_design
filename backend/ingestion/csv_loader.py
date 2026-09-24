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
