## Backend Setup

**Use this command to get all the needed dependencies:**

```
pip install -r backend/requirements.txt
```

## SQLite persistence (Sprint 2)

Dataset rows stay in Pandas DataFrames; SQLite only stores dataset metadata,
analysis runs, and diagnostic summaries (see `backend/models/records.py` for
the table columns).

```text
Dataset -> Pandas DataFrame -> Diagnostics
                                  |
                                  v
                            AnalysisService -> Repository -> SQLite
```

Diagnostics (`backend/diagnostics/`) return a standardized
`DiagnosticResult` schema (`backend/models/schemas.py`) — `diagnostic`,
`column`, `severity`, `value`, `message`, `recommendation`, `metadata` — before
`AnalysisService` persists them through the repository. This is separate from
`records.DiagnosticResult`, the SQLAlchemy table, and is meant to also cover
future statistical/fairness checks (KS tests, ANOVA, regression, fairness
metrics).

Timestamps are stored as naive UTC. Foreign keys are enforced, so a bad
`dataset_id`/`analysis_id` is rejected rather than silently orphaned.

### Run an analysis

```python
import pandas as pd

from backend.database import create_sqlite_engine, initialize_database, session_scope
from backend.database.repository import get_dataset, list_diagnostic_results
from backend.services.analysis_service import AnalysisService

engine = create_sqlite_engine()  # defaults to <project>/data/analysis.sqlite3
initialize_database(engine)

try:
    df = pd.DataFrame({"sensor": ["A", "A", "B"], "reading": [10, 10, None]})
    service = AnalysisService(engine)
    dataset = service.register_dataset(df, name="Sensor readings", source="example")
    analysis = service.run_analysis(dataset.id, df)

    with session_scope(engine) as session:
        results = list_diagnostic_results(session, analysis.id)
        for result in results:
            print(result.diagnostic_type, result.column_name, result.value, result.message)
finally:
    engine.dispose()
```

Pass `create_sqlite_engine("path/to/db.sqlite3")` for a different file, or
`":memory:"` for an isolated in-memory database. Register a dataset once, then
call `run_analysis(dataset.id, df)` per run; a failed run is marked `failed`
and rolls back any partial findings.

### Use the repository directly

```python
from backend.database.repository import create_dataset, list_datasets

with session_scope(engine) as session:
    dataset = create_dataset(
        session, name="Survey", source="upload", file_name="survey.csv",
        row_count=120, column_count=8,
    )
    datasets = list_datasets(session)
```

`session_scope` commits on success, rolls back on error, and always closes the
session. Repository functions expect a session — they never commit it
themselves.

### Tests

```text
python -m pytest test/ -v
```
