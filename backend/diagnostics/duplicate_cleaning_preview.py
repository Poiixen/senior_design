"""Non-destructive preview of removing exact duplicate rows.

The only supported action is ``remove_exact_duplicates``: every row that is
identical to an earlier row in all columns is proposed for removal, and the
first occurrence is kept. The duplicate definition is the one used by
``detect_duplicates`` (``DataFrame.duplicated``), so the removed count always
equals that diagnostic's ``duplicate_count``.

- Missing values: two missing values in the same column count as equal, so
  rows that differ only by which cells are missing are not duplicates, while
  rows with missing values in the same cells and equal elsewhere are.
- Row order: kept rows stay in their original order. Nothing is re-sorted
  or re-indexed in the data; row references are 1-based positions among the
  data rows (header excluded), in file order.
- The input DataFrame is never modified. Only row references are returned,
  never cell values.
"""

import hashlib

import pandas as pd

ACTION_REMOVE_EXACT_DUPLICATES = "remove_exact_duplicates"
SUPPORTED_ACTIONS = (ACTION_REMOVE_EXACT_DUPLICATES,)

MAX_PREVIEW_GROUPS = 10
MAX_ROWS_PER_GROUP = 10


def dataset_fingerprint(df: pd.DataFrame) -> str:
    """Stable content hash, so a preview is tied to the exact rows analyzed."""
    digest = hashlib.sha256()
    digest.update("\x1f".join(str(column) for column in df.columns).encode("utf-8"))
    digest.update(str(len(df)).encode("ascii"))
    if len(df) and df.shape[1]:
        row_hashes = pd.util.hash_pandas_object(df, index=False).to_numpy()
        digest.update(row_hashes.tobytes())
    return digest.hexdigest()


def preview_duplicate_removal(df: pd.DataFrame) -> dict:
    """Describe what removing exact duplicate rows would do, without doing it."""
    original_rows = len(df)
    is_duplicate = df.duplicated(keep="first").to_numpy()
    removed_rows = int(is_duplicate.sum())

    groups = []
    group_count = 0
    if removed_rows:
        # Group by position so repeated column names do not break grouping.
        keys = [df.iloc[:, i].reset_index(drop=True) for i in range(df.shape[1])]
        group_ids = pd.Series(
            df.reset_index(drop=True).groupby(keys, dropna=False, sort=False).ngroup()
        )
        positions = pd.Series(range(original_rows))
        kept_position = positions.groupby(group_ids).transform("min")
        removed_by_kept = (
            positions[is_duplicate].groupby(kept_position[is_duplicate]).agg(list)
        )
        group_count = len(removed_by_kept)
        for kept, removed in removed_by_kept.sort_index().head(MAX_PREVIEW_GROUPS).items():
            groups.append({
                "kept_row": int(kept) + 1,
                "removed_rows": [int(row) + 1 for row in removed[:MAX_ROWS_PER_GROUP]],
                "removed_count": len(removed),
            })

    return {
        "original_row_count": original_rows,
        "removed_row_count": removed_rows,
        "resulting_row_count": original_rows - removed_rows,
        "duplicate_group_count": group_count,
        "groups": groups,
        "groups_truncated": group_count > len(groups),
    }
