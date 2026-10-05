# Team Science

Dataset-agnostic data quality pipeline. Takes a tabular dataset, validates its
structure, profiles the columns, runs diagnostics for missing values,
duplicates and outliers, and persists the findings behind an API.

**UCI Adult Income is the first development dataset, not the only supported
one.** Every stage takes an arbitrary `pandas.DataFrame`. Adult-specific
handling is confined to [adult_adapter.py](backend/ingestion/adult_adapter.py),
and the unit tests pass with no dataset on disk.

## Architecture

```
              Any Dataset
                   │
                   ▼
          Generic Ingestion
                   │
            ┌──────┴──────┐
            │             │
       Generic CSV   Dataset Adapter
                          │
                   (when necessary)
            │             │
            └──────┬──────┘
                   ▼
              Validation
                   ▼
               Profiling
                   ▼
          Diagnostics Engine
                   ▼
        Standard Result Schema
                   ▼
           ┌───────┴───────┐
           ▼               ▼
        Database          API
                            ▼
                     Future Dashboard
```

Well-formed CSVs go through `load_csv()`. Datasets with quirks get an adapter
that normalizes them first. Everything downstream sees a plain DataFrame.

## Setup

Python 3.12, Node 24.

```bash
python -m venv .venv

source .venv/bin/activate      # macOS / Linux
.venv\Scripts\activate         # Windows (cmd / PowerShell)
source .venv/Scripts/activate  # Windows (Git Bash)

pip install -r backend/requirements.txt
```

## Database

SQLite at `data/analysis.sqlite3`. Initialization is explicit — importing the
module touches nothing.

```python
from backend.database.connection import create_sqlite_engine, initialize_database

engine = create_sqlite_engine()      # or ":memory:"
initialize_database(engine)          # adds missing tables, keeps existing rows
```

Tables: `datasets`, `analyses`, `diagnostic_results`. Raw rows are never
stored, only metadata and findings. Group writes with `session_scope(engine)`.

## API

```bash
uvicorn backend.api.main:app --reload
```

`GET /health`, and `POST /api/analyze` taking a CSV upload. Docs at `/docs`.

## Frontend

React Router app.

```bash
cd frontend
npm install
npm run dev        # hot reload
npm run build
npm run typecheck
```

## Tests

```bash
python -m pytest                        # everything
python -m pytest -m "not integration"   # no dataset required
python -m pytest -m integration         # real Adult data only
```

Run from the repo root. [pyproject.toml](pyproject.toml) puts the root on
`sys.path`, so test files need no `sys.path` manipulation.

Tests marked `integration` use the real Adult files and skip when `data/raw/`
is absent. Everything else uses fixtures from [test/conftest.py](test/conftest.py),
supplied by naming one as an argument:

```python
def test_something(simple_clean_df):
    assert profile_dataset(simple_clean_df)["rows"] == 6
```

| Fixture | Contents |
| --- | --- |
| `simple_clean_df` | 6 rows, no problems, 2 numeric + 1 categorical |
| `missing_values_df` | 100 rows; missing at 0%, 3%, 10%, 40% |
| `duplicate_rows_df` | 8 rows, 2 duplicates (25%) |
| `numeric_outliers_df` | bounds -5.0..15.0, 2 outliers, plus clean and text columns |
| `mixed_types_df` | one column each of int, float, bool, str, datetime |
| `adult_df` / `adult_test_df` | real Adult files via the adapter, session-scoped |

Sizes are pinned to thresholds in the code under test: 100 rows so percentages
land exactly on the severity bands, 8 rows so 2 duplicates is exactly 25%.

## Structure

```
backend/
├── ingestion/
│   ├── csv_loader.py           # load_csv() — any CSV
│   └── adult_adapter.py        # load_adult() — the only Adult-aware module
├── diagnostics/                # all take a plain DataFrame
│   ├── validate_dataset.py
│   ├── generic_dataset_profiler.py
│   ├── missing_value_detection.py
│   ├── duplicate_detection.py
│   └── iqr_outlier_detection.py
├── models/
│   ├── records.py              # SQLAlchemy tables
│   └── schemas.py              # DiagnosticResult
├── database/
│   ├── connection.py           # engine, init, session_scope
│   └── repository.py
├── services/
│   └── analysis_service.py     # diagnostics -> persistence
└── api/main.py                 # FastAPI
test/                           # conftest.py + test_*.py
data/raw/UCI_ADULT_INCOME/      # development dataset
frontend/                       # React Router app
pyproject.toml                  # pytest config
```

## Module reference

| Entry point | Returns |
| --- | --- |
| `load_csv(path, **options)` | DataFrame. Forwards `**options` to `pandas.read_csv`. Raises `FileNotFoundError`, `PermissionError`, `CSVLoadError` |
| `load_adult(path)` | DataFrame. Adult only: 15 column names, `?` to NaN, strips padding, drops the `.` from test labels |
| `validate_dataset(df)` | `valid`, `rows`, `columns`, `warnings` |
| `profile_dataset(df)` | Shape, numeric/categorical split, per-column details, embedded duplicate and missing reports |
| `detect_missing_values(df)` | Per column with missing data: count, percentage, severity (`none`/`low`/`moderate`/`high` at 0/5%/20%) |
| `detect_duplicates(df)` | `duplicate_count`, `duplicate_percentage` — repeats only, not first occurrences |
| `detect_outliers_iqr(df, column)` | Quartiles, bounds, outlier count and percentage. Default multiplier 1.5 |
| `detect_numeric_outliers(df)` | The above for every numeric column |
| `AnalysisService(engine).register_dataset(df, name=...)` | `Dataset` row — metadata and dimensions only |
| `AnalysisService(engine).run_analysis(dataset_id, df)` | `Analysis` row. Validates first; blocking errors skip profiling, missing values, duplicates and outliers. Findings commit together or the run is marked failed |
| `AnalysisService(engine).list_findings(analysis_id)` | Saved `DiagnosticResult` rows for a run |

Percentages are 0–100. Outlier bounds are inclusive.

## Adding a dataset

1. Raw files go in `data/raw/<NAME>/`. Large files aren't committed — document
   where to get them.
2. Try `load_csv()` first. It forwards any `pandas.read_csv` keyword, which
   usually covers delimiters, encodings and column names.
3. Write an adapter only if the file needs reshaping to be usable.
4. Add unit tests with generic fixtures; anything needing the real files gets
   `@pytest.mark.integration`.

## Adding an adapter

Takes a path, returns a clean DataFrame. No diagnostics, no analysis. Create
`backend/ingestion/<name>_adapter.py`:

```python
def load_mydata(file_path: str) -> pd.DataFrame:
    df = load_csv(file_path, ...)
    # rename columns, coerce types, map missing markers to NaN
    return df
```

- Build on `load_csv()`, not `pandas.read_csv`, so errors stay consistent.
- Raise `CSVLoadError` when the layout doesn't match.
- Keep dataset-specific constants in this module. A column name from your
  dataset appearing in `backend/diagnostics/` means the abstraction leaked.

## Adding a diagnostic

Pure function, DataFrame in, findings out. No I/O, no database, no knowledge
of which dataset it's looking at. Create `backend/diagnostics/<name>.py`:

```python
def detect_something(df: pd.DataFrame) -> dict:
    """One line on what it detects."""
    return {"metric": ..., "percentage": ...}
```

- `df` first; tuning values as keyword arguments with defaults.
- An empty DataFrame must not raise — guard division by zero.
- `KeyError` for a missing column, `TypeError` for a wrong dtype,
  `ValueError` for a bad parameter.
- Percentages 0–100.

Return `DiagnosticResult` (`diagnostic`, `column`, `severity`, `value`,
`message`, `recommendation`, `metadata`) so findings persist and serialize
uniformly. Add it to `profile_dataset()` if it belongs in the standard
profile. Tests must pass without the Adult dataset.
