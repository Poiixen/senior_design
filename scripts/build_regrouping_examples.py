"""Regenerate docs/examples/regrouping from the real endpoint (Ticket #58).

Usage, from the repo root (needs the test dependencies):
    python scripts/build_regrouping_examples.py

Each file holds the request, the HTTP status and the response, so teammates
building on the regrouping results can see exact shapes. The datasets are the
ones in docs/examples/demo-pack.
"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, ".")
from fastapi.testclient import TestClient  # noqa: E402

from backend.api.main import app, configure_database  # noqa: E402

PACK = pathlib.Path("docs/examples/demo-pack")
OUT = pathlib.Path("docs/examples/regrouping")

SPARSE = "datasets/sparse_categories.csv"
IDENTIFIERS = "datasets/identifier_like.csv"
BASE = {"comparison_type": "categorical_categorical", "group_column": "education", "outcome_column": "income"}
DEGREE = [{"label": "Degree", "categories": ["BA", "MA", "PhD"]}]
GRADUATE = [{"label": "Graduate", "categories": ["MA", "PhD"]}]
AGE = {"comparison_type": "categorical_numeric", "group_column": "education", "value_column": "age"}
SPEND = {"comparison_type": "categorical_numeric", "group_column": "customer_id", "value_column": "spend"}

EXAMPLES = [
    ("identifier_warning", "A flagged identifier-like grouping column: the comparison still runs, with the reasons as a warning.", IDENTIFIERS, [], SPEND),
    ("identifier_confirmed", "The same selection after the user confirms the column is meaningful.", IDENTIFIERS, [], {**SPEND, "confirm_columns": ["customer_id"]}),
    ("sparse_comparison", "A sparse categorical comparison: expected-count warnings and details, no regrouping.", SPARSE, [], BASE),
    ("valid_combination", "BA, MA and PhD combined into Degree, run after the original comparison so both are referenced.", SPARSE, [BASE], {**BASE, "category_mappings": {"education": DEGREE}}),
    ("regrouped_with_remaining_warnings", "A combination that still leaves small expected counts; the warnings stay visible.", SPARSE, [], {**BASE, "category_mappings": {"education": GRADUATE}}),
    ("method_change", "Regrouping four groups into two changes the automatic method from Kruskal-Wallis to Welch's t-test.", SPARSE, [], {**AGE, "category_mappings": {"education": DEGREE}}),
    ("invalid_label_collision", "An invalid mapping is rejected with 400 and nothing is saved.", SPARSE, [], {**BASE, "category_mappings": {"education": [{"label": "HS", "categories": ["MA", "PhD"]}]}}),
]


def run(name, description, dataset, prior, request):
    configure_database(app, pathlib.Path(tempfile.mkdtemp()) / "a.sqlite3")
    client = TestClient(app)
    client.post("/api/auth/register", json={"email": "u@example.com", "password": "correct-horse"})
    csv = (PACK / dataset).read_text(encoding="utf-8")
    analysis_id = client.post("/api/analyze", files={"file": (pathlib.Path(dataset).name, csv, "text/csv")}).json()["analysis_id"]
    url = f"/api/reports/{analysis_id}/comparisons"
    for earlier in prior:
        client.post(url, json=earlier)
    response = client.post(url, json=request)
    document = {
        "description": description,
        "dataset": f"docs/examples/demo-pack/{dataset}",
        "earlier_requests": prior,
        "request": request,
        "status": response.status_code,
        "response": response.json(),
    }
    (OUT / f"{name}.json").write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(name, response.status_code)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.json"):
        stale.unlink()
    for example in EXAMPLES:
        run(*example)
