import math
import numpy as np
import pandas as pd

from backend.diagnostics.duplicate_detection import detect_duplicates
from backend.diagnostics.missing_value_detection import detect_missing_values


def safe_number(value):
    """Convert numeric statistics into JSON-safe Python values."""

    if pd.isna(value):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(number):
        return None

    return number


def profile_dataset(df: pd.DataFrame) -> dict:

    # Column types
    numeric_columns = []
    categorical_columns = []

    # Rest of the info
    column_details = []

    total_rows = len(df)

    # Diagnose column type
    for column_name in df.columns:

        column = df[column_name]

        # General column statistics
        non_null_count = int(column.count())
        missing_count = int(column.isna().sum())
        unique_values = int(column.nunique(dropna=True))

        missing_percentage = (
            round((missing_count / total_rows) * 100, 2)
            if total_rows > 0 else None
        )

        unique_percentage = (
            round((unique_values / non_null_count) * 100, 2)
            if non_null_count > 0 else None
        )

        # Populate column details
        details = {
            "name": column_name,
            "dtype": str(column.dtype),
            "non_null_count": non_null_count,
            "missing_count": missing_count,
            "missing_percentage": missing_percentage,
            "unique_values": unique_values,
            "unique_percentage": unique_percentage
        }

        # Numeric columns
        if pd.api.types.is_numeric_dtype(column):

            inferred_category = "numeric"
            numeric_columns.append(column_name)

            valid_column = pd.to_numeric(
                column, errors="coerce"
            )

            # Convert Boolean values to numbers for statistics
            if pd.api.types.is_bool_dtype(column):
                valid_column = valid_column.astype(float)

            # Remove infinity and missing values
            valid_column = valid_column.replace(
                [np.inf, -np.inf], np.nan
            ).dropna()

            details.update({
                "mean": safe_number(valid_column.mean()),
                "median": safe_number(valid_column.median()),
                "std_dev": safe_number(valid_column.std()),
                "min": safe_number(valid_column.min()),
                "q1": safe_number(valid_column.quantile(0.25)),
                "q3": safe_number(valid_column.quantile(0.75)),
                "max": safe_number(valid_column.max())
            })

        # Categorical columns
        else:

            inferred_category = "categorical"
            categorical_columns.append(column_name)

            valid_column = column.dropna()

            if not valid_column.empty:

                counts = valid_column.value_counts()

                most_common_value = counts.index[0]
                most_common_count = int(counts.iloc[0])

                most_common_percentage = round(
                    (most_common_count / non_null_count) * 100, 2
                )

                # Convert common scalar values to Python types
                if hasattr(most_common_value, "item"):
                    most_common_value = most_common_value.item()

                if isinstance(most_common_value, (pd.Timestamp, pd.Timedelta)):
                    most_common_value = str(most_common_value)

            else:
                most_common_value = None
                most_common_count = None
                most_common_percentage = None

            details.update({
                "most_common_value": most_common_value,
                "most_common_count": most_common_count,
                "most_common_percentage": most_common_percentage
            })

        details["category"] = inferred_category

        column_details.append(details)

    return {
        "rows": len(df),
        "columns": len(df.columns),
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
        "duplicates": detect_duplicates(df),
        "missing_values": detect_missing_values(df),
        "column_details": column_details,
    }