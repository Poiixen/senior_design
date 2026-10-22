import pandas as pd

"""
    name    email country
0  Alice  a@x.com      US
1  Alice  a@x.com      US 
2  Alice  a@x.com      US
3    Bob  b@x.com      CA 
4    Bob  b@x.com      CA 
5  Carol  a@x.com      US
6    Dan  d@x.com      CA
7    Eve  e@x.com      US
8  Frank  f@x.com      US
9   Gina  g@x.com      CA

returns: 
{
  "duplicate_count": 3,  (aka how many rows are extra?)
  "duplicate_percentage": 30.0, (aka what percentage of total is a duplicate. 3/10 == 30%)
  "duplicate_group_count": 2, (how many distinct entries are duplicated. i.e. Alice is one, Bob is two)
  "rows_in_duplicate_groups": 5, (what is the total including of all og + og_duplicates
  "largest_duplicate_group_size": 3, (largest # of rows in one distinct group)
  "duplicate_columns": ["email", "name"], (which cols are duplicated)
  "repeated_value_summary": [
    {"column_name": "email", "repeated_values": 2, "rows_affected": 6},
    {"column_name": "name",  "repeated_values": 2, "rows_affected": 5}
  ]
}
"""

DISTINCT_RATIO_THRESHOLD = 0.5


def _largest_group_size(duplicate_rows: pd.DataFrame) -> int:
    if duplicate_rows.empty:
        return 0
    # Group by position so repeated column names do not break the grouping.
    keys = [duplicate_rows.iloc[:, i] for i in range(duplicate_rows.shape[1])]
    return int(duplicate_rows.groupby(keys, dropna=False, sort=False).size().max())


def _repeated_value_summary(df: pd.DataFrame) -> list:
    """Counts of repeated values in identifier-like columns."""
    deduplicated = df.drop_duplicates()
    summary = []
    for i, column_name in enumerate(df.columns):
        distinct_values = deduplicated.iloc[:, i].dropna()
        if distinct_values.empty:
            continue
        if distinct_values.nunique() / len(distinct_values) <= DISTINCT_RATIO_THRESHOLD:
            continue

        counts = df.iloc[:, i].value_counts(dropna=True)
        repeated = counts[counts > 1]
        if repeated.empty:
            continue

        summary.append({
            "column_name": str(column_name),
            "repeated_values": int(len(repeated)),
            "rows_affected": int(repeated.sum()),
        })

    summary.sort(key=lambda entry: entry["rows_affected"], reverse=True)
    return summary


def detect_duplicates(df: pd.DataFrame) -> dict:
    duplicate_count = int(df.duplicated().sum())
    duplicate_percentage = (duplicate_count / len(df)) * 100 if len(df) > 0 else 0.0

    in_duplicate_group = df.duplicated(keep=False)
    rows_in_duplicate_groups = int(in_duplicate_group.sum())
    # Every group keeps exactly one first occurrence; the rest are duplicates.
    duplicate_group_count = rows_in_duplicate_groups - duplicate_count

    repeated_value_summary = _repeated_value_summary(df) if df.shape[1] > 0 else []

    return {
        "duplicate_count": duplicate_count,
        "duplicate_percentage": duplicate_percentage,
        "duplicate_group_count": duplicate_group_count,
        "rows_in_duplicate_groups": rows_in_duplicate_groups,
        "largest_duplicate_group_size": _largest_group_size(df[in_duplicate_group]),
        "duplicate_columns": [entry["column_name"] for entry in repeated_value_summary],
        "repeated_value_summary": repeated_value_summary,
    }
