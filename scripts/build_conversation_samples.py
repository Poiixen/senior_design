"""Regenerate docs/examples/conversations from the real endpoints.

The model is a scripted stand-in, so the samples are reproducible and need no
credentials; the report, comparison, sources and storage are the real ones.

Usage, from the repo root (needs the test dependencies):
    python scripts/build_conversation_samples.py
"""
import sys, json, tempfile, pathlib, os
sys.path.insert(0, "test"); sys.path.insert(0, ".")
os.environ.pop("ANTHROPIC_API_KEY", None)
from fastapi.testclient import TestClient
from backend.api.main import app, configure_database
import test_api_suggestions as t

OUT = pathlib.Path("docs/examples/conversations")
OUT.mkdir(parents=True, exist_ok=True)
for f in OUT.glob("*.json"):
    f.unlink()


def fresh():
    d = tempfile.mkdtemp()
    configure_database(app, pathlib.Path(d) / "a.sqlite3")
    c = TestClient(app)
    c.post("/api/auth/register", json={"email": "u@example.com", "password": "correct-horse"})
    app.state.conversation_complete = None
    return c


def scripted(source_ids, text, sufficient=True):
    return lambda system, user: json.dumps(
        {"sufficient_evidence": sufficient, "answer": text, "source_ids": source_ids}
    )


def save(name, note, request, response):
    (OUT / f"{name}.json").write_text(
        json.dumps({"description": note, "request": request, "response": response}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def post(c, a, body):
    return c.post(f"/api/reports/{a}/questions", json=body)


c = fresh(); a = t.upload(c); cid = t.compare(c, a, "group", "score")

# 1 unavailable: no AI credentials. The question is still saved.
body = {"question": "Why was the group difference flagged?", "request_id": "q-1"}
r = post(c, a, body).json()
save("unavailable", "No AI credentials (or the provider failed or returned an invalid reply). HTTP 200 with status 'unavailable'; the question is saved.", body, r)
conversation = r["conversation_id"]

# 2 the same request_id retried once the AI is available: answered, still one saved question
app.state.conversation_complete = scripted(
    [f"finding:group_difference-c{cid}", f"comparison:{cid}"],
    "It was surfaced because Welch's independent-samples t-test compared the mean score of the two groups and the observed gap was large. The comparison carries a warning about small groups, so check those groups for skew or outliers.")
r = post(c, a, body).json()
save("answered_after_retry", "Retry with the same request_id: the saved question is reused (same message_id) and answered. Sources are backend descriptors of the saved results used.", body, r)

# 3 replayed: retrying an answered request returns the stored answer, no new model call
r = post(c, a, {**body, "conversation_id": conversation}).json()
save("replayed", "A client retry of an already answered request returns the stored answer with replayed=true and saves nothing new.", {**body, "conversation_id": conversation}, r)

# 4 follow-up in the same conversation, with an honest limitation
app.state.conversation_complete = scripted(
    [], "The report has no ANOVA result, so I cannot say what an ANOVA showed. The saved comparison used Welch's independent-samples t-test.", sufficient=False)
body2 = {"question": "What did the ANOVA show?", "request_id": "q-2", "conversation_id": conversation}
save("insufficient_evidence", "The report does not contain the requested analysis. The answer says so plainly and cites no sources.", body2, post(c, a, body2).json())

# 5 history, list, and a new empty conversation
save("history", "GET /api/reports/{id}/conversations/{conversation_id}: every saved message, oldest first.", None,
     c.get(f"/api/reports/{a}/conversations/{conversation}").json())
save("conversation_list", "GET /api/reports/{id}/conversations: this user's threads for the report, newest first.", None,
     c.get(f"/api/reports/{a}/conversations").json())
save("conversation_created", "POST /api/reports/{id}/conversations (201): an empty thread.", None,
     c.post(f"/api/reports/{a}/conversations").json())
print("wrote", len(list(OUT.glob("*.json"))), "samples")
