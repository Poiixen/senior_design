import pandas as pd

from backend.diagnostics.duplicate_detection import detect_duplicates
from backend.diagnostics.missing_value_detection import detect_missing_values

def profile_dataset(df: pd.DataFrame) -> dict:
    'column types'
    numeric_columns = []
    categorical_columns = []

    'rest of the info'
    column_details = []

    'diagnose column type'
    for column_name in df.columns:

        column = df[column_name]

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
            "unique_values": int(column.nunique(dropna=True))
        })

    return {
        "rows": len(df),
        "columns": len(df.columns),
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "duplicates": detect_duplicates(df),
        "missing_values": detect_missing_values(df),
        "column_details": column_details,
    }
    