"""Interquartile range (IQR) outlier detection for numeric columns."""

import pandas as pd
from pandas.api.types import is_numeric_dtype

DEFAULT_MULTIPLIER = 1.5

def detect_outliers_iqr(df: pd.DataFrame, column: str, multiplier: float = DEFAULT_MULTIPLIER) -> dict:
    """detect outliers in a single numeric column using the IQR method.
    output:
        {
            'column_name': str,
            'q1': float,
            'q3': float,
            'iqr': float,
            'lower_bound': float,
            'upper_bound': float,
            'outlier_count': int,
            'outlier_percentage': float,
        }

    edge cases checked:
        KeyError: If the column is not present in the DataFrame.
        TypeError: If the column is not numeric.
        ValueError: If the multiplier is negative.
    """
    if column not in df.columns:
        raise KeyError(f"Column not found in DataFrame: {column}")

    series = df[column]
    if not is_numeric_dtype(series):
        raise TypeError(f"Column is not numeric: {column} (dtype={series.dtype})")

    if multiplier < 0:
        raise ValueError(f"IQR multiplier must be non-negative, got {multiplier}")

    values = series.dropna()
    valid_count = len(values)

    if valid_count == 0:
        return {
            'column_name': column,
            'q1': float('nan'),
            'q3': float('nan'),
            'iqr': float('nan'),
            'lower_bound': float('nan'),
            'upper_bound': float('nan'),
            'outlier_count': 0,
            'outlier_percentage': 0.0,
        }

    q1 = float(values.quantile(0.25))
    q3 = float(values.quantile(0.75))
    iqr = q3 - q1
    lower_bound = q1 - multiplier * iqr
    upper_bound = q3 + multiplier * iqr

    outlier_count = int(((values < lower_bound) | (values > upper_bound)).sum())

    return {
        'column_name': column,
        'q1': q1,
        'q3': q3,
        'iqr': iqr,
        'lower_bound': lower_bound,
        'upper_bound': upper_bound,
        'outlier_count': outlier_count,
        'outlier_percentage': outlier_count / valid_count * 100,
    }


def detect_numeric_outliers(df: pd.DataFrame, multiplier: float = DEFAULT_MULTIPLIER) -> list:
    """run the IQR check on each numeric column; non-numeric columns are skipped."""
    numeric_columns = df.select_dtypes(include='number').columns
    return [detect_outliers_iqr(df, column, multiplier) for column in numeric_columns]