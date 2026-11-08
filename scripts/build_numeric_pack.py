"""Build the numeric analysis demo pack in docs/examples/numeric-pack (Ticket #57).

Usage, from the repo root (needs the backend and test dependencies, scipy >= 1.16):
    python scripts/build_numeric_pack.py

Writes small synthetic CSV files, ``cases.json``, ``README.md`` and ``responses/``.

* ``cases.json`` expectations are calculated here directly with pandas and scipy,
  never with the backend, so ``test/test_numeric_pack.py`` compares the application
  against an independent calculation.
* ``responses/`` holds the real API response for every case, so Ticket #47 and #55
  can build against exact shapes. The test replays them so they cannot go stale.

Fixed seeds keep the output identical between runs.
"""

import json
import pathlib
import sys
import tempfile

import numpy as np
import pandas as pd
from scipy import stats

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "examples" / "numeric-pack"
DATA = OUT / "datasets"
RESPONSES = OUT / "responses"
BASE_URL = "http://127.0.0.1:8000"
REL, ABS = 1e-6, 1e-9


# --- datasets ------------------------------------------------------------------------------


def centred(rs, n, mean, sd):
    """Normal draws shifted so the sample mean is exactly ``mean`` before rounding."""
    values = rs.normal(0, sd, n)
    return values - values.mean() + mean


rs = np.random.RandomState(57)
datasets = {}

# Two groups whose means differ by exactly 5 (before rounding to 3 decimals).
datasets["two_groups"] = pd.DataFrame(
    {
        "group": ["control"] * 40 + ["treatment"] * 35,
        "score": np.round(np.concatenate([centred(rs, 40, 50, 8), centred(rs, 35, 55, 8)]), 3),
    }
)

# Four departments of unequal size and spread. Hours differ; satisfaction does not.
sizes = {"A": 50, "B": 35, "C": 20, "D": 12}
hours = {"A": (40, 4), "B": (44, 6), "C": (47, 9), "D": (38, 3)}
datasets["departments"] = pd.DataFrame(
    {
        "department": [d for d, n in sizes.items() for _ in range(n)],
        "hours": np.round(np.concatenate([rs.normal(*hours[d], n) for d, n in sizes.items()]), 2),
        "satisfaction": np.round(rs.normal(70, 10, sum(sizes.values())), 1),
    }
)

# Missing group labels and missing, NaN and infinite measurements.
messy = pd.DataFrame(
    {
        "site": ["north"] * 15 + ["south"] * 15,
        "reading": np.round(rs.normal(20, 3, 30), 2).astype(object),
    }
)
messy.loc[[2, 17], "site"] = ""
messy.loc[[4, 19], "reading"] = ""
messy.loc[[6], "reading"] = "NaN"
messy.loc[[8], "reading"] = "inf"
messy.loc[[21], "reading"] = "-inf"
messy.loc[[2], "reading"] = ""  # missing both: counted under both reasons
datasets["messy"] = messy

# Constant values and too few observations.
datasets["constant"] = pd.DataFrame(
    {
        "team": ["x"] * 5 + ["y"] * 5 + ["z"] * 5,
        "pair_group": ["solo"] + ["many"] * 14,
        "fixed": [7.0] * 15,
        "rare": [3.5, 9.25] + [None] * 13,
        "spread": np.round(rs.normal(10, 2, 15), 2),
    }
)

# Distribution shapes.
base = rs.lognormal(0, 0.6, 300) * 10
datasets["shapes"] = pd.DataFrame(
    {
        "right_skewed": np.round(base, 3),
        "left_skewed": np.round(100 - base, 3),
        "symmetric": np.round(rs.normal(50, 10, 300), 3),
    }
)

DATA.mkdir(parents=True, exist_ok=True)
for stale in DATA.glob("*.csv"):
    stale.unlink()
for name, frame in datasets.items():
    frame.to_csv(DATA / f"{name}.csv", index=False)


# --- independent expectations ----------------------------------------------------------------


def load(dataset):
    """Read the CSV back the way a user's upload is read: blanks and 'NaN' are missing."""
    return pd.read_csv(DATA / dataset)


def finite_rows(df, group, value):
    values = pd.to_numeric(df[value], errors="coerce")
    usable = df[group].notna() & np.isfinite(values)
    return df.loc[usable, group], values[usable].astype(float)


def ordered_labels(labels):
    counts = labels.value_counts()
    return sorted(counts.index, key=lambda label: (-int(counts[label]), str(label)))


def summary(prefix, values):
    values = np.asarray(values, dtype=float)
    q1, median, q3 = np.quantile(values, [0.25, 0.5, 0.75])
    fence = 1.5 * (q3 - q1)
    inside = values[(values >= q1 - fence) & (values <= q3 + fence)]
    expected = {
        "count": int(len(values)),
        "mean": float(values.mean()),
        "median": float(median),
        "min": float(values.min()),
        "q1": float(q1),
        "q3": float(q3),
        "max": float(values.max()),
        "whisker_low": float(inside.min()),
        "whisker_high": float(inside.max()),
        "outlier_count": int(len(values) - len(inside)),
    }
    if len(values) > 1:
        expected["std_dev"] = float(values.std(ddof=1))
    return {f"{prefix}.{key}": value for key, value in expected.items()}


def comparison_expect(dataset, group, value, method):
    df = load(dataset)
    labels_column, values = finite_rows(df, group, value)
    labels = ordered_labels(labels_column)
    arrays = [values[labels_column == label].to_numpy() for label in labels]
    expect = {
        "rows.total": len(df),
        "rows.included": int(len(values)),
        "rows.exclusion_reasons.missing_group_value": int(df[group].isna().sum()),
        "rows.exclusion_reasons.missing_or_non_finite_value": int(
            (~np.isfinite(pd.to_numeric(df[value], errors="coerce"))).sum()
        ),
        **summary("overall", values),
    }
    for index, (label, array) in enumerate(zip(labels, arrays)):
        expect[f"groups.{index}.label"] = label
        expect.update(summary(f"groups.{index}", array))

    selected = method if method != "auto" else ("welch_t_test" if len(labels) == 2 else "kruskal_wallis")
    expect["method_selection.selected"] = selected
    expect["test.method.key"] = selected
    return expect, labels, arrays


def welch_expect(arrays):
    result = stats.ttest_ind(*arrays, equal_var=False)
    interval = result.confidence_interval(0.95)
    return {
        "test.status": "ok",
        "test.statistic": float(result.statistic),
        "test.degrees_of_freedom": float(result.df),
        "test.p_value": float(result.pvalue),
        "test.mean_difference": float(arrays[0].mean() - arrays[1].mean()),
        "test.mean_difference_ci.lower": float(interval.low),
        "test.mean_difference_ci.upper": float(interval.high),
    }


def anova_expect(arrays):
    result = stats.f_oneway(*arrays, equal_var=False)  # Welch's ANOVA, scipy >= 1.16
    combined = np.concatenate(arrays)
    total = ((combined - combined.mean()) ** 2).sum()
    between = sum(len(a) * (a.mean() - combined.mean()) ** 2 for a in arrays)
    return {
        "test.status": "ok",
        "test.statistic": float(result.statistic),
        "test.degrees_of_freedom_between": len(arrays) - 1,
        "test.p_value": float(result.pvalue),
        "test.eta_squared": float(between / total),
    }


def kruskal_expect(arrays):
    result = stats.kruskal(*arrays)
    return {
        "test.status": "ok",
        "test.statistic": float(result.statistic),
        "test.degrees_of_freedom": len(arrays) - 1,
        "test.p_value": float(result.pvalue),
    }


def shape_expect(dataset, column):
    values = pd.to_numeric(load(dataset)[column], errors="coerce").to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 3 or np.ptp(values) == 0:
        return {"distribution_shape.status": "unavailable", "distribution_shape.sample_size": int(len(values)),
                "distribution_shape.skewness": None}, None
    skewness = float(stats.skew(values, bias=False))
    if abs(skewness) < 0.5:
        classification, strength = "approximately_symmetric", None
    else:
        classification = "right_skewed" if skewness > 0 else "left_skewed"
        strength = "strong" if abs(skewness) >= 1 else "moderate"
    return {
        "distribution_shape.status": "ok",
        "distribution_shape.sample_size": int(len(values)),
        "distribution_shape.skewness": skewness,
        "distribution_shape.classification": classification,
        "distribution_shape.strength": strength,
        "histogram.included_values": int(len(values)),
    }, skewness


def request(group, value, method):
    body = {"comparison_type": "categorical_numeric", "group_column": group, "value_column": value}
    if method != "auto":
        body["method"] = method
    return body


cases = []


def comparison_case(case_id, title, question, dataset, group, value, method, *, result, outcome,
                    warnings=(), absent=(), reason=None, visual, notes):
    expect, labels, arrays = comparison_expect(dataset, group, value, method)
    if result == "welch":
        expect.update(welch_expect(arrays))
    elif result == "anova":
        expect.update(anova_expect(arrays))
    elif result == "kruskal":
        expect.update(kruskal_expect(arrays))
    else:
        expect["test.status"] = "unavailable"
    cases.append(
        {
            "id": case_id, "ticket": 57, "kind": "comparison", "outcome": outcome, "title": title,
            "question": question, "dataset": f"datasets/{dataset}",
            "columns": {"group_column": group, "value_column": value},
            "request": request(group, value, method), "expected_status": 201, "expect": expect,
            "expected_warnings_contain": list(warnings), "expected_absent_warnings": list(absent),
            "expected_reason_contains": reason, "visual": visual, "notes": notes,
        }
    )
    return arrays


arrays = comparison_case(
    "two_groups_known_difference", "Two independent groups with a known mean difference",
    "Is the mean score different for control and treatment?",
    "two_groups.csv", "group", "score", "welch_t_test", result="welch", outcome="success",
    absent=["fewer than 30"],
    visual="Per-group mean chart with the mean difference and its 95% confidence interval; grouped box plot.",
    notes="Groups were generated with means of exactly 50 and 55 (difference -5 after rounding to 3 "
          "decimals: control minus treatment). Both groups have at least 30 rows, so no warnings.",
)
assert abs(arrays[0].mean() - arrays[1].mean() + 5) < 1e-3

arrays = comparison_case(
    "anova_unequal_groups", "Welch's ANOVA across four groups of unequal size and spread",
    "Does mean weekly hours differ across departments?",
    "departments.csv", "department", "hours", "welch_anova", result="anova", outcome="warning",
    warnings=["fewer than 30"],
    visual="Group summary table and grouped box plot of hours by department; eta squared beside it.",
    notes="Sizes 50/35/20/12 with standard deviations 4/6/9/3, the case Welch's ANOVA is for. C and D "
          "have fewer than 30 rows, so a normality warning is returned. The test does not say which "
          "departments differ.",
)
assert stats.f_oneway(*arrays, equal_var=False).pvalue < 0.001

comparison_case(
    "auto_three_groups_rank_based", "Default method for three or more groups stays Kruskal-Wallis",
    "Same selection without a method: do hours tend to be higher in some departments?",
    "departments.csv", "department", "hours", "auto", result="kruskal", outcome="success",
    absent=["fewer than 5"],
    visual="Grouped box plot; label the result as a rank comparison, not a comparison of means.",
    notes="Existing requests without `method` keep the Ticket #51 behaviour; analysis_question.key is compare_ranks.",
)

arrays = comparison_case(
    "anova_no_strong_evidence", "Comparison without strong evidence of a difference",
    "Does mean satisfaction differ across departments?",
    "departments.csv", "department", "satisfaction", "welch_anova", result="anova", outcome="warning",
    warnings=["fewer than 30"],
    visual="Per-group means with overlapping spreads.",
    notes="All departments were drawn from the same distribution. A large p-value is not proof the "
          "departments are equal; the method's limitations say so.",
)
assert stats.f_oneway(*arrays, equal_var=False).pvalue > 0.1

comparison_case(
    "missing_and_non_finite", "Missing group labels and missing, NaN and infinite measurements",
    "Does the mean reading differ between sites, once unusable rows are left out?",
    "messy.csv", "site", "reading", "welch_t_test", result="welch", outcome="warning",
    warnings=["fewer than 30"],
    visual="Group summary table with included and excluded row counts.",
    notes="Row 3 is missing both values and is counted under both reasons; excluded rows are counted once.",
)

comparison_case(
    "anova_constant_values", "Constant measurement",
    "Does the mean of a constant column differ across teams?",
    "constant.csv", "team", "fixed", "welch_anova", result=None, outcome="unavailable",
    reason="zero variance",
    visual="Group summary table only; no test result.",
    notes="Every group has zero variance, so Welch's weights are undefined. Summaries are still returned.",
)

comparison_case(
    "welch_insufficient_observations", "Group with a single observation",
    "Is the mean spread different for the solo row and the rest?",
    "constant.csv", "pair_group", "spread", "welch_t_test", result=None, outcome="unavailable",
    reason="at least two values",
    visual="Group summary table only; no test result or confidence interval.",
    notes="A group of one has no standard deviation, so the t-test and interval cannot be calculated.",
)

comparison_case(
    "anova_with_two_groups", "Method that does not fit the number of groups",
    "Welch's ANOVA requested for two groups.",
    "two_groups.csv", "group", "score", "welch_anova", result=None, outcome="unavailable",
    reason="welch_t_test",
    visual="Prompt the user to switch to Welch's t-test.",
    notes="Welch's ANOVA is offered for three or more groups; the reason points to welch_t_test.",
)


def profile_case(case_id, title, dataset, column, *, outcome, visual, notes, reason=None, warnings=False):
    expect, _ = shape_expect(dataset, column)
    cases.append(
        {
            "id": case_id, "ticket": 57, "kind": "profile", "outcome": outcome, "title": title,
            "question": f"What is the shape of the '{column}' distribution?",
            "dataset": f"datasets/{dataset}", "columns": {"column": column}, "request": None,
            "expected_status": 200, "expect": expect, "expected_reason_contains": reason,
            "expects_shape_warning": warnings, "visual": visual, "notes": notes,
        }
    )


profile_case("shape_right_skewed", "Right-skewed distribution", "shapes.csv", "right_skewed", outcome="success",
             visual="Histogram with 'strongly right-skewed' beside it.",
             notes="Log-normal values: a long tail of large values.")
profile_case("shape_left_skewed", "Left-skewed distribution", "shapes.csv", "left_skewed", outcome="success",
             visual="Histogram with 'strongly left-skewed' beside it.",
             notes="The mirror image of right_skewed, so the skewness has the same size and opposite sign.")
profile_case("shape_symmetric", "Approximately symmetric distribution", "shapes.csv", "symmetric", outcome="success",
             visual="Histogram with 'approximately symmetric'; do not call it normal.",
             notes="Normal draws. Approximate symmetry is reported, never normality.")
profile_case("shape_constant", "Constant column", "constant.csv", "fixed", outcome="unavailable",
             reason="identical", visual="Histogram of a single bar; no shape description.",
             notes="Skewness is undefined with no spread.")
profile_case("shape_insufficient", "Too few observations", "constant.csv", "rare", outcome="unavailable",
             reason="at least 3", visual="No shape description.",
             notes="Only 2 finite values; at least 3 are needed.")
profile_case("shape_small_sample", "Small sample", "constant.csv", "spread", outcome="warning",
             warnings=True, visual="Histogram with the shape marked as tentative.",
             notes="15 values: the description is returned with an instability warning.")

assert {c["expect"]["distribution_shape.classification"] for c in cases if c["id"] in
        ("shape_right_skewed", "shape_left_skewed", "shape_symmetric")} == {
    "right_skewed", "left_skewed", "approximately_symmetric"}

(OUT / "cases.json").write_text(
    json.dumps({"rel_tolerance": REL, "abs_tolerance": ABS, "cases": cases}, indent=2, default=str) + "\n",
    encoding="utf-8",
)


# --- real responses ---------------------------------------------------------------------------


def real_responses():
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient

    from backend.api.main import app, configure_database

    RESPONSES.mkdir(parents=True, exist_ok=True)
    for stale in RESPONSES.glob("*.json"):
        stale.unlink()
    for case in cases:
        configure_database(app, pathlib.Path(tempfile.mkdtemp()) / "a.sqlite3")
        client = TestClient(app)
        client.post("/api/auth/register", json={"email": "u@example.com", "password": "correct-horse"})
        csv = (OUT / case["dataset"]).read_text(encoding="utf-8")
        report = client.post("/api/analyze", files={"file": (pathlib.Path(case["dataset"]).name, csv, "text/csv")})
        if case["kind"] == "profile":
            profile = next(p for p in report.json()["column_profiles"] if p["name"] == case["columns"]["column"])
            status, response = report.status_code, profile
        else:
            reply = client.post(f"/api/reports/{report.json()['analysis_id']}/comparisons", json=case["request"])
            status, response = reply.status_code, reply.json()
        document = {
            "case": case["id"], "outcome": case["outcome"], "dataset": f"docs/examples/numeric-pack/{case['dataset']}",
            "request": case["request"], "status": status, "response": response,
        }
        (RESPONSES / f"{case['id']}.json").write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(case["id"], status)


real_responses()


# --- README ----------------------------------------------------------------------------------


def fmt(value):
    return f"{value:.4g}" if isinstance(value, float) else json.dumps(value)


HEADLINE_KEYS = (
    "rows.included", "test.status", "test.statistic", "test.degrees_of_freedom",
    "test.degrees_of_freedom_between", "test.p_value", "test.mean_difference",
    "test.mean_difference_ci.lower", "test.mean_difference_ci.upper", "test.eta_squared",
    "distribution_shape.status", "distribution_shape.skewness", "distribution_shape.classification",
    "distribution_shape.strength", "distribution_shape.sample_size",
)

lines = [
    "# Numeric analysis demo pack (Ticket #57)",
    "",
    "Small synthetic datasets, runnable requests, expected results and real responses for",
    "Welch's t-test, Welch's ANOVA, Kruskal-Wallis and distribution-shape descriptions.",
    "",
    "* `datasets/` - the CSV files.",
    "* `cases.json` - every case, with expected values calculated directly with pandas and",
    "  scipy (never with the backend). Numeric tolerance: relative 1e-6, absolute 1e-9;",
    "  counts and labels must match exactly.",
    "* `responses/` - the real API response for each case (success, warning and unavailable",
    "  examples for Tickets #47 and #55).",
    "",
    "Rebuild everything with `python scripts/build_numeric_pack.py` (needs scipy >= 1.16 for",
    "`f_oneway(equal_var=False)`). `python -m pytest test/test_numeric_pack.py` runs every case",
    "through the API, checks it against `cases.json`, checks saved results reopen unchanged,",
    "and checks `responses/` still match the endpoint.",
    "",
    "## Run it by hand",
    "",
    "Start the backend (`./run-all.sh` or `uvicorn backend.api.main:app`), then from this folder:",
    "",
    "```bash",
    "python ../../../scripts/dev_seed.py   # creates dev1@example.com / devpassword1",
    f"curl -c jar.txt -H 'Content-Type: application/json' -d '{{\"email\":\"dev1@example.com\",\"password\":\"devpassword1\"}}' {BASE_URL}/api/auth/login",
    f"ID=$(curl -s -b jar.txt -F file=@datasets/departments.csv {BASE_URL}/api/analyze | python -c 'import json,sys; print(json.load(sys.stdin)[\"analysis_id\"])')",
    "```",
    "",
    "Each case below gives its own upload and request. Afterwards:",
    "",
    "```bash",
    f"curl -b jar.txt {BASE_URL}/api/reports/$ID/comparisons                 # saved results, with method and evidence",
    f"curl -b jar.txt {BASE_URL}/api/reports/$ID                             # column_profiles[].distribution_shape",
    f"curl -b jar.txt -H 'Content-Type: application/json' -d '{{}}' {BASE_URL}/api/reports/$ID/suggestions   # Ticket #47",
    "```",
    "",
    "## Demo script",
    "",
    "1. Upload `two_groups.csv` and run **two_groups_known_difference**: Welch's t-test, the mean",
    "   difference (control minus treatment, about -5) and its 95% confidence interval.",
    "2. Upload `departments.csv` and run **anova_unequal_groups**: Welch's ANOVA with F, both",
    "   degrees of freedom, eta squared and the small-group warning. Then run",
    "   **auto_three_groups_rank_based** to show the default stays the rank-based Kruskal-Wallis.",
    "3. Upload `shapes.csv` and open the report: each numeric profile has `distribution_shape`",
    "   next to the unchanged `histogram`.",
    "4. `GET .../comparisons` reopens the saved results unchanged. Each group carries count,",
    "   mean, median, SD, quartiles, whiskers and outlier counts for the charts; `POST",
    "   .../suggestions` explains them without recalculating anything.",
    "",
    "## Cases",
    "",
]
for case in cases:
    lines += [f"### {case['id']} ({case['outcome']})", "", f"**{case['title']}.** {case['question']}", "",
              f"* Dataset: `{case['dataset']}`",
              "* Columns: " + ", ".join(f"{k} = `{v}`" for k, v in case["columns"].items())]
    if case["kind"] == "comparison":
        body = json.dumps(case["request"])
        lines += [
            "* Request:",
            "",
            "  ```bash",
            f"  curl -b jar.txt -H 'Content-Type: application/json' -d '{body}' {BASE_URL}/api/reports/$ID/comparisons",
            "  ```",
            "",
            f"* Expected HTTP status: {case['expected_status']}",
        ]
    else:
        lines += [f"* Request: `curl -b jar.txt {BASE_URL}/api/reports/$ID` and read the `{case['columns']['column']}` entry of `column_profiles`."]
    headline = [f"`{key}` = {fmt(case['expect'][key])}" for key in HEADLINE_KEYS if key in case["expect"]]
    lines.append("* Expected: " + "; ".join(headline) + ". Group summaries are in `cases.json`.")
    for text in case.get("expected_warnings_contain") or []:
        lines.append(f"* Warning contains: \"{text}\"")
    for text in case.get("expected_absent_warnings") or []:
        lines.append(f"* No warning containing: \"{text}\"")
    if case.get("expects_shape_warning"):
        lines.append("* `distribution_shape.warnings` says the estimate is unstable.")
    if case.get("expected_reason_contains"):
        lines.append(f"* Unavailable reason contains: \"{case['expected_reason_contains']}\"")
    lines += [f"* Supports: {case['visual']}", f"* Notes: {case['notes']}",
              f"* Real response: `responses/{case['id']}.json`", ""]
(OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
print(f"wrote {len(cases)} cases and {len(datasets)} datasets to {OUT}")
