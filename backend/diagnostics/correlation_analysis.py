"""Pearson correlation matrix for numeric columns."""

from math import isfinite

import pandas as pd
from pandas.api.types import is_numeric_dtype


def calculate_correlation_matrix(df: pd.DataFrame) -> dict:
    """Return Pearson correlations between numeric columns, JSON-safe.

    output:
        {
            'columns': [str, ...],
            'matrix': [[float | None, ...], ...],
        }

    matrix[i][j] is the correlation of columns[i] and columns[j]. Missing
    values are dropped pairwise. Unavailable values (constant columns, too
    few overlapping rows, non-finite results) are None. Boolean columns count
    as numeric, matching the profiler and outlier diagnostics. With no numeric
    columns the result is {'columns': [], 'matrix': []}.
    """
    numeric_columns = [
        column for column in df.columns if is_numeric_dtype(df[column])
    ]
    if not numeric_columns:
        return {"columns": [], "matrix": []}

    numeric = df[numeric_columns].astype("float64")
    corr = numeric.corr(method="pearson")

    matrix = []
    for row_column in numeric_columns:
        row = []
        for col_column in numeric_columns:
            value = float(corr.loc[row_column, col_column])
            if not isfinite(value):
                row.append(None)
            else:
                row.append(max(-1.0, min(1.0, value)))
        matrix.append(row)

    return {"columns": [str(column) for column in numeric_columns], "matrix": matrix}
