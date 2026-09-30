import pandas as pd

from backend.diagnostics.validate_dataset import validate_dataset
from backend.diagnostics.generic_dataset_profiler import profile_dataset
from backend.diagnostics.missing_value_detection import detect_missing_values
from backend.diagnostics.duplicate_detection import detect_duplicates
from backend.diagnostics.iqr_outlier_detection import detect_numeric_outliers


def analyze_dataset(df: pd.DataFrame) -> dict:
    validate_dataset(df)

    if not isinstance(df, pd.DataFrame):
        return {
            "profile": {},
            "diagnostics": []
        }

    profile = profile_dataset(df)

    missing_values = detect_missing_values(df)
    duplicates = detect_duplicates(df)
    outliers = detect_numeric_outliers(df)

    return {
        "profile": profile,
        "diagnostics": [
            {
                "type": "missing_values",
                "results": missing_values
            },
            {
                "type": "duplicates",
                "results": duplicates
            },
            {
                "type": "outliers",
                "results": outliers
            }
        ]
    }