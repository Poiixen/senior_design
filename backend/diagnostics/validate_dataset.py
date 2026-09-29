import pandas as pd

' Csv file loaded, now we check for any data issues. Quality check.'
def validate_dataset(df: pd.DataFrame) -> dict:
    warnings = []

    'check dataframe sturcutre and if it is supported.'
    if not isinstance(df, pd.DataFrame):
        'doesnt append, just returns warning message'
        return {
            "valid": False,
            "rows": 0,
            "columns": 0,
            "warnings": ["Input is not a pandas DataFrame"],
        }
    row_count, column_count = df.shape

    'DATASET--'

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