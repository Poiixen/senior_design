"""Build the synthetic demo pack in docs/examples/demo-pack (Ticket #58).

Usage, from the repo root:
    python scripts/build_demo_pack.py

Writes small CSV files, ``cases.json`` and ``README.md``. Every expected value
is calculated here directly with pandas and scipy, never with the backend, so
the API tests compare the application against an independent calculation.
Fixed seeds keep the output identical between runs.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

OUT = Path(__file__).resolve().parents[1] / "docs" / "examples" / "demo-pack"
DATA = OUT / "datasets"
BASE_URL = "http://127.0.0.1:8000"
REL = 1e-6


def rounded(values, digits=1):
    return [round(float(v), digits) for v in values]


# --- datasets ------------------------------------------------------------------------------

rs = np.random.RandomState(58)
datasets = {}

datasets["identifier_like"] = pd.DataFrame(
    {
        "customer_id": [f"C{i:03d}" for i in range(40)],
        "region_id": ["R1", "R2", "R3", "R4"] * 10,
        "segment": ["A", "B", "C", "D"] * 10,
        "spend": rounded(rs.normal(100, 15, 40)),
    }
)
cities = [f"City{i:02d}" for i in range(12)]
datasets["high_cardinality_grouping"] = pd.DataFrame(
    {
        "city": [city for city in cities for _ in range(10)],
        "spend": rounded(rs.normal(100, 15, 120)),
    }
)
education = ["HS"] * 30 + ["BA"] * 25 + ["MA"] * 3 + ["PhD"] * 2
datasets["sparse_categories"] = pd.DataFrame(
    {
        "education": education,
        "income": [
            "high" if rs.random_sample() < {"HS": 0.3, "BA": 0.6, "MA": 0.8, "PhD": 1.0}[level] else "low"
            for level in education
        ],
        "age": rounded(rs.normal(40, 8, 60)),
    }
)

DATA.mkdir(parents=True, exist_ok=True)
for stale in DATA.glob("*.csv"):
    stale.unlink()
for name, frame in datasets.items():
    frame.to_csv(DATA / f"{name}.csv", index=False)


# --- independent expectations ----------------------------------------------------------------


def chi_square_expect(df, group, outcome, mapping=None):
    groups = df[group].copy()
    for label, members in (mapping or {}).items():
        groups = groups.replace({member: label for member in members})
    table = pd.crosstab(groups, df[outcome])
    statistic, p_value, dof, expected = stats.chi2_contingency(table.to_numpy(), correction=False)
    return {
        "test.statistic": float(statistic),
        "test.p_value": float(p_value),
        "test.degrees_of_freedom": int(dof),
        "test.expected_count_summary.cells": int(expected.size),
        "test.expected_count_summary.cells_below_5": int((expected < 5).sum()),
    }


def counts(series):
    series = series.dropna()
    result = series.value_counts()
    order = sorted(result.index, key=lambda label: (-int(result[label]), str(label)))
    return [{"label": label, "count": int(result[label])} for label in order]


cases = []
sparse = datasets["sparse_categories"]
degree = [{"label": "Degree", "categories": ["BA", "MA", "PhD"]}]
graduate = [{"label": "Graduate", "categories": ["MA", "PhD"]}]
base_request = {"comparison_type": "categorical_categorical", "group_column": "education", "outcome_column": "income"}

cases.append(
    {
        "id": "identifier_warning", "ticket": 58, "title": "Identifier-like grouping column",
        "question": "Is customer_id a meaningful grouping for spend?",
        "dataset": "datasets/identifier_like.csv",
        "request": {"comparison_type": "categorical_numeric", "group_column": "customer_id", "value_column": "spend"},
        "expected_status": 201,
        "expect": {"identifier_review.0.column": "customer_id", "identifier_review.0.likely_identifier": True,
                   "identifier_review.0.confirmed": False, "identifier_review.0.signals.distinct_values": 40},
        "expected_warnings_contain": ["may be an identifier"],
        "visual": "Warning beside the result with the reasons; no chart should be trusted until the user confirms.",
        "notes": "40 of 40 values are distinct. The existing category limit is unchanged.",
    }
)
cases.append(
    {
        "id": "identifier_confirmed", "ticket": 58, "title": "User confirms the flagged column",
        "question": "Same selection, with customer_id confirmed as meaningful.",
        "dataset": "datasets/identifier_like.csv",
        "request": {"comparison_type": "categorical_numeric", "group_column": "customer_id", "value_column": "spend",
                    "confirm_columns": ["customer_id"]},
        "expected_status": 201,
        "expect": {"identifier_review.0.confirmed": True},
        "expected_absent_warnings": ["may be an identifier"],
        "visual": "The reasons stay visible and show as confirmed.",
        "notes": "Confirmation removes the warning but keeps the reasons on record.",
    }
)
cases.append(
    {
        "id": "name_alone_is_not_flagged", "ticket": 58, "title": "Identifier-like name with repeating values",
        "question": "Is region_id (4 repeating values) flagged?",
        "dataset": "datasets/identifier_like.csv",
        "request": {"comparison_type": "categorical_numeric", "group_column": "region_id", "value_column": "spend"},
        "expected_status": 201, "expect": {}, "expected_absent_keys": ["identifier_review"],
        "visual": "No warning.", "notes": "A name alone never flags a column.",
    }
)
cases.append(
    {
        "id": "legitimate_high_cardinality", "ticket": 58, "title": "Legitimate high-cardinality grouping column",
        "question": "Does spend differ across 12 cities?",
        "dataset": "datasets/high_cardinality_grouping.csv",
        "request": {"comparison_type": "categorical_numeric", "group_column": "city", "value_column": "spend"},
        "expected_status": 201, "expect": {"test.method.key": "kruskal_wallis", "test.status": "ok"},
        "expected_absent_keys": ["identifier_review"],
        "visual": "Grouped summary of 12 cities.", "notes": "12 distinct values in 120 rows (10%) is not flagged.",
    }
)
cases.append(
    {
        "id": "sparse_comparison", "ticket": 58, "title": "Sparse categorical comparison",
        "question": "Is income distributed differently across education levels?",
        "dataset": "datasets/sparse_categories.csv", "request": base_request, "expected_status": 201,
        "expect": chi_square_expect(sparse, "education", "income"),
        "expected_warnings_contain": ["expected counts below 5"],
        "visual": "Grouped percentage bars; MA and PhD have 3 and 2 rows.", "notes": "No regrouping: the baseline.",
    }
)


def regrouping_case(case_id, title, question, request, mapping, relabelled, *, warnings=(), absent=(), notes, visual):
    mapped = {item["label"]: item["categories"] for item in mapping}
    replacements = {member: label for label, members in mapped.items() for member in members}
    regrouped_counts = counts(sparse["education"].replace(replacements))
    cases.append(
        {
            "id": case_id, "ticket": 58, "title": title, "question": question,
            "dataset": "datasets/sparse_categories.csv",
            "request": request, "expected_status": 201,
            "expect": {
                **chi_square_expect(sparse, "education", "income", mapped),
                "regrouping.columns.0.categories_before": 4,
                "regrouping.columns.0.categories_after": len(regrouped_counts),
                "regrouping.columns.0.rows_relabelled": relabelled,
                "regrouping.method_change.changed": False,
            },
            "expect_counts": {"before": counts(sparse["education"]), "after": regrouped_counts},
            "expect_mapping": {"education": mapping},
            "expected_warnings_contain": list(warnings),
            "expected_absent_warnings": list(absent),
            "visual": visual, "notes": notes,
        }
    )


regrouping_case(
    "valid_combination", "Valid user-defined combination",
    "Is income distributed differently for HS versus a combined Degree group (BA, MA, PhD)?",
    {**base_request, "category_mappings": {"education": degree}}, degree, 30,
    absent=["expected counts below 5"],
    visual="Before/after category-count bar chart.",
    notes="Four groups become two. The mapping, original counts and regrouped counts are returned. A different p-value is not evidence the regrouping is better.",
)
regrouping_case(
    "regrouped_with_remaining_warnings", "Regrouped comparison that still has reliability warnings",
    "Is income distributed differently once only MA and PhD are combined into Graduate?",
    {**base_request, "category_mappings": {"education": graduate}}, graduate, 5,
    warnings=["expected counts below 5"],
    visual="Before/after counts; the remaining warning stays beside the chart.",
    notes="Graduate has only 5 rows, so expected counts are still small. The warning is not hidden by regrouping.",
)
cases.append(
    {
        "id": "method_changes", "ticket": 58, "title": "Combination that changes the number of groups and the method",
        "question": "Does age differ by education when everyone above high school is combined?",
        "dataset": "datasets/sparse_categories.csv",
        "request": {"comparison_type": "categorical_numeric", "group_column": "education", "value_column": "age",
                    "category_mappings": {"education": degree}},
        "expected_status": 201,
        "expect": {
            "regrouping.method_change.group_count_before": 4,
            "regrouping.method_change.group_count_after": 2,
            "regrouping.method_change.method_before": "kruskal_wallis",
            "regrouping.method_change.method_after": "welch_t_test",
            "regrouping.method_change.changed": True,
            "test.method.key": "welch_t_test",
        },
        "visual": "Before/after counts plus a notice that the method changed from a rank to a mean comparison.",
        "notes": "Four groups use Kruskal-Wallis; two groups use Welch's t-test.",
    }
)
cases.append(
    {
        "id": "regroup_both_columns", "ticket": 58, "title": "Regroup the group and the outcome column",
        "question": "Mappings can be given for both categorical columns of a categorical comparison.",
        "dataset": "datasets/sparse_categories.csv",
        "request": {**base_request, "category_mappings": {"education": degree,
                                                          "income": [{"label": "below", "categories": ["low"]}]}},
        "expected_status": 201,
        "expect": {"regrouping.columns.0.column": "education", "regrouping.columns.1.column": "income",
                   "regrouping.columns.1.categories_after": 2},
        "visual": "Before/after charts for both columns.",
        "notes": "Renaming a single category is allowed. Unmapped categories keep their labels.",
    }
)

invalid = [
    ("invalid_unknown_category", "Unknown category", {"education": [{"label": "X", "categories": ["Nope"]}]}, "does not exist"),
    ("invalid_conflicting_mapping", "Category in two combinations",
     {"education": [{"label": "X", "categories": ["MA"]}, {"label": "Y", "categories": ["MA", "PhD"]}]}, "mapped to both"),
    ("invalid_empty_label", "Empty label", {"education": [{"label": "  ", "categories": ["MA"]}]}, "empty label"),
    ("invalid_label_collision", "Label collides with an existing category",
     {"education": [{"label": "HS", "categories": ["MA", "PhD"]}]}, "collides"),
    ("invalid_wrong_type", "Number given for a text category", {"education": [{"label": "X", "categories": [5]}]}, "(int)"),
    ("invalid_column", "Mapping for a column that is not selected", {"age": [{"label": "X", "categories": ["a"]}]}, "not one of them"),
]
for case_id, title, mapping, needle in invalid:
    cases.append(
        {
            "id": case_id, "ticket": 58, "title": f"Invalid mapping: {title}",
            "question": "The request must be rejected with a clear message and save nothing.",
            "dataset": "datasets/sparse_categories.csv",
            "request": {**base_request, "category_mappings": mapping},
            "expected_status": 400, "expect": {}, "expected_detail_contains": needle,
            "visual": "An inline error beside the mapping controls.", "notes": "400 responses create no comparison.",
        }
    )

(OUT / "cases.json").write_text(
    json.dumps({"rel_tolerance": REL, "abs_tolerance": 1e-9, "cases": cases}, indent=2, default=str) + "\n",
    encoding="utf-8",
)


# --- README ----------------------------------------------------------------------------------

lines = [
    "# Regrouping demo pack",
    "",
    "Small synthetic datasets and runnable requests for Ticket #58 (identifier warnings and",
    "category regrouping). Everything here is generated by `python scripts/build_demo_pack.py`,",
    "which calculates the expected values directly with pandas and scipy.",
    "`test/test_demo_pack.py` runs every case through the API and compares it with `cases.json`",
    "using the stated tolerances.",
    "",
    "## Run a case by hand",
    "",
    "```bash",
    "python scripts/dev_seed.py            # creates dev1@example.com / devpassword1",
    f"curl -c jar.txt -H 'Content-Type: application/json' -d '{{\"email\":\"dev1@example.com\",\"password\":\"devpassword1\"}}' {BASE_URL}/api/auth/login",
    f"curl -b jar.txt -F file=@datasets/sparse_categories.csv {BASE_URL}/api/analyze   # note analysis_id",
    f"curl -b jar.txt -H 'Content-Type: application/json' -d '<request body below>' {BASE_URL}/api/reports/$ID/comparisons",
    f"curl -b jar.txt {BASE_URL}/api/reports/$ID/comparisons              # reopen the saved results",
    f"curl -b jar.txt -X POST {BASE_URL}/api/reports/$ID/suggestions      # explanations (Ticket #47)",
    "```",
    "",
    "Run from `docs/examples/demo-pack`. Numeric tolerances are a relative 1e-6; counts must match exactly.",
    "",
]
for case in cases:
    lines += [f"## {case['id']} (Ticket #{case['ticket']})", "", f"**{case['title']}.** {case['question']}", "",
              f"* Dataset: `{case['dataset']}`", "* Request body:", "", "  ```json", "  " + json.dumps(case["request"]), "  ```", "",
              f"* Expected HTTP status: {case['expected_status']}"]
    if case.get("expect"):
        lines.append("* Expected values: see `cases.json` (`expect`).")
    for key, label in (("expected_warnings_contain", "Warning contains"), ("expected_absent_warnings", "No warning containing")):
        for item in case.get(key, []):
            lines.append(f"* {label}: \"{item}\"")
    if case.get("expected_detail_contains"):
        lines.append(f"* Error detail contains: \"{case['expected_detail_contains']}\"")
    lines += [f"* Supports: {case['visual']}", f"* Notes: {case['notes']}", ""]
(OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote {len(cases)} cases and {len(datasets)} datasets to {OUT}")
