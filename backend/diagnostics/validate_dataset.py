import pandas as pd

' Csv file loaded, now we check for any data issues. Quality check.'
def validate_dataset(df: pd.DataFrame) -> dict:
    warnings = []
    '''
    Returns:
        dict: Validation results containing:
            - 'valid' (bool): True if no blocking structural errors exist.
            - 'rows' (int): Number of rows in the dataset.
            - 'columns' (int): Number of columns in the dataset.
            - 'errors' (list[str]): Blocking structural errors preventing analysis.
            - 'warnings' (list[str]): Non-blocking data quality warnings.
    '''
    errors = []

    'check dataframe sturcutre and if it is supported.'
    if not isinstance(df, pd.DataFrame):
        'doesnt append, just returns warning message'
        return {
            "valid": False,
            "rows": 0,
            "columns": 0,
            "warnings": ["Input is not a pandas DataFrame"],
            "errors": ["Input is not a pandas DataFrame"]
        }
    
    row_count, column_count = df.shape

    'DATASET--'

    'empty dataset'
    if row_count == 0:
        errors.append("Dataset is empty (0 rows)")

    'zero columns'
    if column_count == 0:
        errors.append("Dataset has zero columns")

    'dupe column names'
    if df.columns.duplicated().any():
        duplicate_columns = df.columns[df.columns.duplicated()].tolist()
        warnings.append(f"Duplicate column names found: {duplicate_columns}, count: {len(duplicate_columns)}")

    if df.columns.duplicated().any():
        duplicate_columns = (
            df.columns[df.columns.duplicated()].unique().tolist()
        )
        errors.append(
            f"Duplicate column names found: {duplicate_columns}, count: {len(duplicate_columns)}"
        )

    'extrememly smalll dataset less then 5'
    if 0 < row_count < 5:
        warnings.append("Dataset is extremely small (fewer than 5 rows)")

    if column_count > 0:
        empty_columns = df.columns[df.isna().all()].tolist()
        if empty_columns:
            warnings.append(
                f"Completely empty columns found: {empty_columns}"
            )

    return {
        "valid": len(errors) == 0,
        "rows": row_count,
        "columns": column_count,
        "errors": errors,
        "warnings": warnings,
    }