"""Regenerate docs/examples/suggestions from the real endpoint.

Usage, from the repo root (needs the test dependencies):
    python scripts/build_suggestion_samples.py
"""
import sys, json, tempfile, pathlib, os
sys.path.insert(0, "test"); sys.path.insert(0, ".")
os.environ.pop("ANTHROPIC_API_KEY", None)
from fastapi.testclient import TestClient
from backend.api.main import app, configure_database
import test_api_suggestions as t

OUT = pathlib.Path("docs/examples/suggestions")
for f in OUT.glob("*.json"):
    f.unlink()

def fresh():
    d = tempfile.mkdtemp()
    configure_database(app, pathlib.Path(d) / "a.sqlite3")
    c = TestClient(app)
    c.post("/api/auth/register", json={"email": "u@example.com", "password": "correct-horse"})
    app.state.suggestion_complete = None
    return c

def save(name, note, request, response):
    (OUT / f"{name}.json").write_text(
        json.dumps({"description": note, "request": request, "response": response}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")

# 1 ranked report with a saved comparison
c = fresh(); a = t.upload(c); cid = t.compare(c, a, "group", "score")
save("ranked_with_warnings", "Missing values, repeated rows and one saved mean comparison; the Welch result carries its group-size warnings.",
     {"comparison_ids": [cid]}, t.suggest(c, a, {"comparison_ids": [cid]}).json())

# 2 paging
save("paged_second_page", "Second page of the same report (limit 2, offset 2).",
     {"limit": 2, "offset": 2}, t.suggest(c, a, {"limit": 2, "offset": 2}).json())

# 3 exploratory (several comparisons)
c = fresh(); a = t.upload(c); t.compare(c, a, "group", "score"); t.compare(c, a, "group", "income")
save("exploratory_comparisons", "Two selected comparisons: both are marked exploratory with the multiple-comparison warning.",
     {}, t.suggest(c, a).json())

# 4 clean
c = fresh(); a = t.upload(c, t.clean_csv())
save("clean_report", "A clean report returns no findings.", {}, t.suggest(c, a).json())

# 5 unavailable test
c = fresh(); a = t.upload(c, "group,score\na,1\na,2\nb,3\n"); t.compare(c, a, "group", "score")
save("unavailable_test", "The test could not run; nothing is concluded and the chart is an evidence table.", {}, t.suggest(c, a).json())

# 6 non-significant
rows = ["id,group,score"] + [f"{i},{'A' if i % 2 == 0 else 'B'},{50 + (i * 7) % 9}" for i in range(40)]
c = fresh(); a = t.upload(c, "\n".join(rows) + "\n"); t.compare(c, a, "group", "score")
save("non_significant", "A comparison that detected no difference; the text does not claim the groups are alike.", {}, t.suggest(c, a).json())

# 6c real regrouped comparison
c = fresh(); a = t.upload(c, t.three_group_csv()); t.post_comparison(c, a, {
    "comparison_type": "categorical_numeric", "group_column": "tier", "value_column": "score",
    "category_mappings": {"tier": [{"label": "upper", "categories": ["mid", "high"]}]}})
save("regrouped_comparison", "A regrouped comparison: before/after counts, the exact mapping and the method change.", {}, t.suggest(c, a).json())

# 7 AI source
c = fresh(); a = t.upload(c); base = t.suggest(c, a).json()
app.state.suggestion_complete = lambda system, user: t.reply_for(base)
save("ai_source", "Same findings with validated AI wording: ranking, evidence and charts are unchanged.", {}, t.suggest(c, a).json())
app.state.suggestion_complete = None
for f in sorted(OUT.glob("*.json")):
    r = json.loads(f.read_text(encoding="utf-8"))["response"]
    print(f.name, r["source"], r["total_findings"], [s["finding_type"] for s in r["suggestions"]])
