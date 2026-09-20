import argparse

import pandas as pd

from backend.ingestion.csv_loader import load_csv


def classify_severity(missing_percentage: float) -> str:
    if missing_percentage == 0:
        return "none"
    if missing_percentage < 5:
        return "low"
    if missing_percentage < 20:
        return "moderate"
    return "high"


def detect_missing_values(df: pd.DataFrame) -> list:

    missing_counts = df.isna().sum()
    missing_percentages = df.isna().mean() * 100

    missing_info = pd.DataFrame({
        'column_name': missing_counts.index,
        'missing_count': missing_counts.values,
        'missing_percentage': missing_percentages.values
    })
    missing_info['severity'] = missing_info['missing_percentage'].apply(classify_severity)
    return missing_info[missing_info['missing_count'] > 0].to_dict(orient='records')


