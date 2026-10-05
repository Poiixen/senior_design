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
                     React Dashboard
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

### Run the full development stack

The Bash launcher is repository-relative and works from any team member's
checkout path. It starts both reload-enabled servers, records their process
IDs under the ignored `.run/` directory, and stops both process trees on
Ctrl+C.

```bash
bash ./run-all.sh
```

If a terminal closes unexpectedly or either development port remains busy,
run the cleanup script before restarting:

```bash
bash ./stop-all.sh
```

The cleanup script first uses this checkout's PID files, then clears listeners
on the two project development ports (`5173` and `8000`) as a fallback.

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

`GET /health`, `POST /api/analyze`, and `GET /api/reports/{analysis_id}`.
Interactive API docs are available at `http://127.0.0.1:8000/docs`.

The upload endpoint accepts multipart form fields:

| Field | Default | Meaning |
| --- | --- | --- |
| `file` | required | CSV file |
| `delimiter` | `,` | Comma, semicolon, tab, or pipe in the upload UI |
| `has_header` | `true` | Whether the first row contains column names |
| `missing_values` | `[]` | JSON array of additional missing-value strings; standard pandas markers remain enabled |

Successful uploads return the complete report, including `analysis_id`. The
frontend opens `/reports/{analysis_id}` and retrieves the saved report from the
API. Reports survive page refreshes and backend restarts. Raw CSV rows are not
retained; only metadata and diagnostic summaries are saved.

## Frontend

React Router v8 dashboard for dataset analysis. Full-stack type safety with
TypeScript and React Router's file-based routing. Styled with Tailwind CSS v4.

### How it works

The frontend is a single-page application with three main routes:

- **Home** (`/`) — Upload CSV form with parsing options (delimiter, header row, custom missing-value markers). Submits to the backend API and redirects to the report on success.
- **Report** (`/reports/:id`) — Displays analysis results: dataset summary, missing-value table (sortable), duplicate count, and numeric outliers. `/reports/sample` is a static demo that works without a backend.
- **Documentation** (`/documentation`) — Guide and reference.

The app is API-driven: it uploads files to `POST /api/analyze` and fetches reports from `GET /api/reports/:id`.
Results persist across page refreshes and backend restarts. Raw CSV rows are never stored, only metadata
and diagnostic findings.

### Running the frontend

Requires **Node.js 22.22.0+** and the backend running separately.

```bash
cd frontend
npm install                # Install dependencies (one time)
npm run dev                # Start dev server with hot reload at http://127.0.0.1:5173
npm run build              # Production build
npm run typecheck          # TypeScript checking
```

### Configuration

Copy `frontend/.env.example` to `frontend/.env` and restart the dev server after changes:

| Setting | Default | Purpose |
| --- | --- | --- |
| `API_PROXY_TARGET` | `http://127.0.0.1:8000` | Backend for development; Vite proxies `/api` requests here |
| `VITE_API_BASE_URL` | empty | Public API origin for production (without `/api`); empty uses same-origin |
| `CORS_ALLOWED_ORIGINS` | local Vite origins | Backend setting: comma-separated frontend origins allowed to call the API |

During development, the Vite proxy makes all requests same-origin, so no CORS setup is needed.
For production, configure your web server to route `/api` to FastAPI or set `VITE_API_BASE_URL`
at build time and ensure the backend allows that origin.

### Report schema

The API response schema is documented in [frontend/app/lib/report.ts](frontend/app/lib/report.ts).
- `dataset` — dimensions (rows and columns)
- `summary` — column counts, duplicate totals, issue total, and execution status
- `missing_values` — all columns with missing counts and severity
- `outliers` — all numeric columns with bounds, counts, and flagged values

`summary.issues_detected` counts distinct problems (one per affected column for missing values,
one per numeric column for outliers, one for duplicates, one per warning), not individual bad cells.
`status: "completed"` indicates successful execution, independent of issue count.

Missing severity: none (0%), low (<5%), moderate (<20%), high (≥20%).
Outliers are flagged for review, not automatically incorrect. Missing and outlier percentages use
appropriate denominators (all rows for missing, non-missing numeric values for outliers).
A JSON `null` measurement displays as **Unavailable**; `0` remains `0`.

### Troubleshooting

| Problem | Fix |
| --- | --- |
| `Cannot find module` errors | Run `npm install` in the frontend folder |
| `react-router requires Node > 22.22.0` | Upgrade Node.js at https://nodejs.org/ |
| Port 5173 already in use | Kill the process on that port or edit `frontend/vite.config.ts` `port` value |
| API calls fail or timeout | Ensure backend is running on `http://127.0.0.1:8000` (or update `API_PROXY_TARGET`) |
| Changes don't appear | Save the file; Vite hot-reloads automatically. If not, restart `npm run dev` |

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

### Continuous integration

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs on every pull request
and on pushes to `main`, as two independent jobs:

| Job | Runs |
| --- | --- |
| Backend tests | `pip install -r backend/requirements.txt`, then `pytest -m "not integration"` |
| Frontend typecheck and build | `npm ci`, `npm run typecheck`, `npm run build` |

Both must pass before merge. A failing job marks the check failed on the pull
request and names the failing step.

CI deselects the `integration` marker, so the real Adult-dataset tests are
**optional** and never gate a merge. Run them yourself with:

```bash
python -m pytest -m integration
```

They need `data/raw/UCI_ADULT_INCOME/` on disk, and skip rather than fail when
it is absent.

Database tests stay isolated from the checkout: `test_database.py` and
`test_analysis_service.py` build each engine under pytest's `tmp_path`, and CI
sets `DATABASE_PATH` to a path in the runner's temp directory so importing the
API cannot create a database inside the working tree.

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

### API-to-database tests

[test/test_api_persistence.py](test/test_api_persistence.py) covers the path
that the endpoint tests and the service tests each only half cover: that one
upload produces findings in the response, the same findings in the database,
and a retrievable report identical to the response.

The API builds its SQLite engine at import time from `DATABASE_PATH`,
defaulting to `data/analysis.sqlite3` inside the repository. To keep test runs
out of the working tree, [test/conftest.py](test/conftest.py) points
`DATABASE_PATH` at a temporary directory before any test module imports the
app, and removes it at exit. An explicit `DATABASE_PATH` still wins, so CI can
set its own. One consequence worth knowing: the engine is a module-level
global, so API tests share a single database for the run rather than getting a
fresh one per test. Assertions are written to not depend on the table being
empty.

### Browser smoke test

The automated tests stop at the API. Run this by hand after changing the
upload form, the report page, or the report schema. Start both services with
`bash run-all.sh` (or `.\run-all.ps1`), then:

1. **Upload.** Open <http://127.0.0.1:5173>, choose a CSV with a known problem
   in it, and submit. `test/` has none on disk; the 20-row fixture at the top
   of [test/test_api_persistence.py](test/test_api_persistence.py) is a good
   one to paste into a file, since its findings are known exactly.
2. **Report display.** The report page should show the row and column counts,
   a missing-values row for `reading` at 10% (severity moderate), one `score`
   outlier, and 2 duplicate rows. An all-missing numeric column shows blank
   quartile bounds rather than `NaN`.
3. **Refresh.** Reload the page. The report is re-fetched from the database by
   its ID, so the same numbers must come back and the URL must stay on
   `/reports/<id>`. Losing the report on refresh means the page is rendering
   from in-memory state instead of the stored report.
4. **Direct navigation.** Paste the same `/reports/<id>` URL into a new tab.
   It should render the same report with no upload step.
5. **History.** Visit `/reports`. The upload should be listed newest first,
   with its filename, row and column counts, and a Completed badge.
6. **Unknown ID.** Visit `/reports/999999999`. The page should report that the
   report was not found, not crash or hang.

`/reports/sample` renders a built-in example and needs no backend, so it
isolates frontend rendering problems from API problems.

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
