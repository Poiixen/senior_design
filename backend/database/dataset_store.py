"""On-disk copies of uploaded datasets for analyses that need the rows again.

Column comparisons cannot be rebuilt from the per-column summaries kept in
the database, so each upload's parsed DataFrame is written to
``<directory>/<dataset_id>.parquet``. Parquet keeps column types, so a
reloaded dataset matches what the diagnostics saw. The database itself still
stores no rows.
"""

import os
from pathlib import Path
from typing import Optional, Union

import pandas as pd
import pyarrow as pa


def _as_text(value) -> Optional[str]:
    if value is None or value is pd.NA or (isinstance(value, float) and value != value):
        return None
    return str(value)


class DatasetStore:
    def __init__(self, directory: Union[str, Path]):
        self.directory = Path(directory).expanduser().resolve()

    def path(self, dataset_id: int) -> Path:
        return self.directory / f"{int(dataset_id)}.parquet"

    def save(self, dataset_id: int, df: pd.DataFrame) -> None:
        """Write the dataset atomically, replacing any earlier copy.

        Columns mixing value types (possible in JSON uploads) cannot be
        stored by Parquet; their non-missing values are saved as text, which
        is how the diagnostics already treat them (as categories).
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        df = df.reset_index(drop=True)
        df.columns = [str(column) for column in df.columns]
        target = self.path(dataset_id)
        partial = target.with_suffix(".parquet.partial")
        try:
            try:
                df.to_parquet(partial, index=False)
            except (pa.ArrowInvalid, pa.ArrowTypeError, pa.ArrowNotImplementedError):
                df = df.copy()
                for column in df.columns:
                    if df[column].dtype == object:
                        df[column] = df[column].map(_as_text)
                df.to_parquet(partial, index=False)
            os.replace(partial, target)
        finally:
            partial.unlink(missing_ok=True)

    def load(self, dataset_id: int) -> Optional[pd.DataFrame]:
        """Return the saved dataset, or None if it was never stored."""
        path = self.path(dataset_id)
        if not path.exists():
            return None
        return pd.read_parquet(path)
