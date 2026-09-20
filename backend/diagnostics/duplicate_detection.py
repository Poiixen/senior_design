import pandas as pd


def detect_duplicates(df: pd.DataFrame) -> dict:
    duplicate_count = int(df.duplicated().sum())
    duplicate_percentage = (duplicate_count / len(df)) * 100 if len(df) > 0 else 0.0

    return {
        "duplicate_count": duplicate_count,
        "duplicate_percentage": duplicate_percentage,
    }
