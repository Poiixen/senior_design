"""POST /api/reports/{id}/suggestions through the API."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.models.suggestions import SuggestionResponse
from conftest import register_user

ROWS = 40


def messy_csv() -> str:
    """40 rows: 10 missing `income`, 4 repeated rows, a group effect on `score`."""
    lines = ["id,group,score,income"]
    for i in range(ROWS - 4):
        group = "A" if i % 2 == 0 else "B"
        score = (10 if group == "A" else 20) + (i * 7) % 5
        income = "" if i < 10 else str(1000 + (i * 37) % 90)
        lines.append(f"{i},{group},{score},{income}")
    lines.extend([lines[-1]] * 4)
    return "\n".join(lines) + "\n"


def clean_csv() -> str:
    lines = ["id,group,score"]
    for i in range(ROWS):
        lines.append(f"{i},{'A' if i % 2 == 0 else 'B'},{(i * 7) % 11}")
    return "\n".join(lines) + "\n"


def upload(client, csv_text=None):
    response = client.post(
        "/api/analyze",
        files={"file": ("data.csv", csv_text or messy_csv(), "text/csv")},
    )
    assert response.status_code == 200
    return response.json()["analysis_id"]


def compare(client, analysis_id, group, value, kind="categorical_numeric"):
    key = "value_column" if kind == "categorical_numeric" else "outcome_column"
    response = client.post(
        f"/api/reports/{analysis_id}/comparisons",
        json={"comparison_type": kind, "group_column": group, key: value},
    )
    assert response.status_code == 201
    return response.json()["comparison_id"]


def suggest(client, analysis_id, body=None):
    return client.post(f"/api/reports/{analysis_id}/suggestions", json=body)


def by_type(body):
    return {s["finding_type"]: s for s in body["suggestions"]}


@pytest.fixture(autouse=True)
def no_ai(monkeypatch):
    """Make sure a developer's real credentials are never used."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app.state.suggestion_complete = None
    yield
    app.state.suggestion_complete = None


def test_fallback_works_without_credentials_and_matches_the_model(auth_client):
    analysis_id = upload(auth_client)

    response = auth_client.post(f"/api/reports/{analysis_id}/suggestions")

    assert response.status_code == 200
    body = response.json()
    SuggestionResponse(**body)
    assert body["source"] == "fallback"
    assert body["analysis_id"] == analysis_id
    types = by_type(body)
    assert "missing_values" in types and "duplicates" in types
    assert types["missing_values"]["affected_columns"] == ["income"]
    assert types["missing_values"]["evidence_values"]["missing_count"] == 10
    assert types["missing_values"]["visual"]["data"]["values"] == [10, 30]
    assert types["duplicates"]["evidence_values"]["duplicate_count"] == 4


def test_every_suggestion_has_traceable_evidence_and_a_visual(auth_client):
    analysis_id = upload(auth_client)
    compare(auth_client, analysis_id, "group", "score")

    body = suggest(auth_client, analysis_id).json()

    assert body["suggestions"]
    for item in body["suggestions"]:
        assert item["evidence"] and item["next_steps"] and item["evidence_refs"]
        assert item["visual"]["chart_type"]
        assert item["visual"]["source"]["analysis_id"] == analysis_id
        assert 0 <= item["priority_percent"] <= 100


def test_group_comparison_is_explained_as_a_mean_comparison(auth_client):
    analysis_id = upload(auth_client)
    comparison_id = compare(auth_client, analysis_id, "group", "score")

    body = suggest(auth_client, analysis_id).json()

    finding = by_type(body)["group_difference"]
    assert body["comparison_ids_used"] == [comparison_id]
    assert finding["evidence_refs"][0]["comparison_id"] == comparison_id
    assert finding["evidence_values"]["comparison_basis"] == "means"
    assert finding["evidence_values"]["significant_at_0_05"] is True
    assert finding["visual"]["chart_type"] == "grouped_box"
    assert "compares the mean" in finding["explanation"]
    assert not finding["exploratory"]


def test_several_comparisons_are_marked_exploratory(auth_client):
    analysis_id = upload(auth_client)
    compare(auth_client, analysis_id, "group", "score")
    compare(auth_client, analysis_id, "group", "income")

    body = suggest(auth_client, analysis_id).json()

    tested = [s for s in body["suggestions"] if s["finding_type"] == "group_difference"]
    assert len(tested) == 2
    assert all(s["exploratory"] for s in tested)
    assert all("exploratory" in " ".join(s["warnings"]) for s in tested)


def test_selected_comparison_ids_limit_the_evidence(auth_client):
    analysis_id = upload(auth_client)
    first = compare(auth_client, analysis_id, "group", "score")
    compare(auth_client, analysis_id, "group", "income")

    body = suggest(auth_client, analysis_id, {"comparison_ids": [first]}).json()

    assert body["comparison_ids_used"] == [first]
    assert [s["finding_type"] for s in body["suggestions"]].count("group_difference") == 1


def test_fingerprint_changes_when_a_comparison_is_added(auth_client):
    analysis_id = upload(auth_client)
    before = suggest(auth_client, analysis_id).json()["evidence_fingerprint"]
    compare(auth_client, analysis_id, "group", "score")

    after = suggest(auth_client, analysis_id).json()["evidence_fingerprint"]

    assert before != after


def test_comparison_from_another_report_is_rejected(auth_client):
    first = upload(auth_client)
    second = upload(auth_client)
    foreign = compare(auth_client, first, "group", "score")

    response = suggest(auth_client, second, {"comparison_ids": [foreign]})

    assert response.status_code == 400
    assert str(foreign) in response.json()["detail"]


def test_other_users_get_404_and_see_nothing(client):
    register_user(client, email="a@example.com")
    analysis_id = upload(client)
    comparison_id = compare(client, analysis_id, "group", "score")
    other = TestClient(app)
    register_user(other, email="b@example.com")

    assert suggest(other, analysis_id).status_code == 404
    assert suggest(other, analysis_id, {"comparison_ids": [comparison_id]}).status_code == 404
    assert suggest(client, analysis_id).status_code == 200


def test_other_users_comparison_id_is_rejected_on_own_report(client):
    register_user(client, email="a@example.com")
    foreign = compare(client, upload(client), "group", "score")
    other = TestClient(app)
    register_user(other, email="b@example.com")
    own = upload(other)

    assert suggest(other, own, {"comparison_ids": [foreign]}).status_code == 400


def test_unknown_report_and_unauthenticated_requests(auth_client, api_engine):
    assert suggest(auth_client, 999).status_code == 404
    assert suggest(TestClient(app), 1).status_code == 401


def test_clean_report_gets_no_invented_problems(auth_client):
    analysis_id = upload(auth_client, clean_csv())

    body = suggest(auth_client, analysis_id).json()

    assert body["suggestions"] == []
    assert body["total_findings"] == 0
    assert body["has_more"] is False


def test_ranking_is_reproducible(auth_client):
    analysis_id = upload(auth_client)
    compare(auth_client, analysis_id, "group", "score")

    first = suggest(auth_client, analysis_id).json()
    second = suggest(auth_client, analysis_id).json()

    assert first == second


def test_paging_reaches_the_remaining_findings(auth_client):
    analysis_id = upload(auth_client)
    compare(auth_client, analysis_id, "group", "score")
    everything = suggest(auth_client, analysis_id, {"limit": 20}).json()
    assert everything["total_findings"] >= 3

    first = suggest(auth_client, analysis_id, {"limit": 2}).json()
    rest = suggest(auth_client, analysis_id, {"limit": 20, "offset": 2}).json()

    assert len(first["suggestions"]) == 2 and first["has_more"] is True
    assert rest["has_more"] is False
    ids = [s["finding_id"] for s in first["suggestions"] + rest["suggestions"]]
    assert ids == [s["finding_id"] for s in everything["suggestions"]]


def test_analyses_without_results_are_listed_as_unavailable(auth_client):
    analysis_id = upload(auth_client)

    body = suggest(auth_client, analysis_id).json()

    assert {"anova", "regrouping"} <= set(body["unavailable_analyses"])
    assert "anova" not in json.dumps([s["explanation"] for s in body["suggestions"]]).lower()


def test_invalid_request_bodies_give_422(auth_client):
    analysis_id = upload(auth_client)

    assert suggest(auth_client, analysis_id, {"limit": 0}).status_code == 422
    assert suggest(auth_client, analysis_id, {"offset": -1}).status_code == 422


def reply_for(body, **overrides):
    items = []
    for s in body["suggestions"]:
        items.append(
            {
                "finding_id": s["finding_id"],
                "title": "Reworded " + s["title"],
                "explanation": "Reworded: " + s["evidence"][0],
                "next_steps": ["Check the source data."],
                **overrides,
            }
        )
    return json.dumps({"suggestions": items})


def test_valid_ai_reply_is_used_but_backend_values_are_unchanged(auth_client):
    analysis_id = upload(auth_client)
    baseline = suggest(auth_client, analysis_id).json()
    seen = {}

    def complete(system, user):
        seen["user"] = user
        return reply_for(baseline)

    app.state.suggestion_complete = complete
    body = suggest(auth_client, analysis_id).json()

    assert body["source"] == "ai"
    assert body["suggestions"][0]["title"].startswith("Reworded")
    for ai, plain in zip(body["suggestions"], baseline["suggestions"]):
        assert ai["finding_id"] == plain["finding_id"]
        assert ai["evidence_values"] == plain["evidence_values"]
        assert ai["visual"] == plain["visual"]
        assert ai["priority_percent"] == plain["priority_percent"]
    # Aggregates only: no uploaded values such as ids or incomes are sent.
    assert "1037" not in seen["user"] and "data.csv" not in seen["user"]


@pytest.mark.parametrize(
    "complete",
    [
        lambda system, user: "not json",
        lambda system, user: json.dumps({"suggestions": []}),
        lambda system, user: (_ for _ in ()).throw(RuntimeError("provider down")),
    ],
    ids=["not-json", "missing-findings", "provider-error"],
)
def test_bad_ai_output_falls_back(auth_client, complete):
    analysis_id = upload(auth_client)
    baseline = suggest(auth_client, analysis_id).json()

    app.state.suggestion_complete = complete
    body = suggest(auth_client, analysis_id).json()

    assert body == baseline
    assert body["source"] == "fallback"


def test_ai_reply_with_invented_numbers_or_banned_claims_falls_back(auth_client):
    analysis_id = upload(auth_client)
    baseline = suggest(auth_client, analysis_id).json()

    for override in (
        {"explanation": "Exactly 987654 rows are affected."},
        {"explanation": "You should delete these rows."},
    ):
        app.state.suggestion_complete = lambda system, user, o=override: reply_for(baseline, **o)
        assert suggest(auth_client, analysis_id).json() == baseline


# --- real Ticket #57 and #58 results ------------------------------------------------------


def three_group_csv() -> str:
    lines = ["tier,score,spend"]
    for i in range(36):
        tier = ["low", "mid", "high"][i % 3]
        base = {"low": 20, "mid": 26, "high": 33}[tier]
        lines.append(f"{tier},{base + (i * 7) % 5},{100 + (i * 13) % 40}")
    return "\n".join(lines) + "\n"


def post_comparison(client, analysis_id, body):
    response = client.post(f"/api/reports/{analysis_id}/comparisons", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_real_kruskal_result_stays_a_rank_comparison(auth_client):
    analysis_id = upload(auth_client, three_group_csv())
    post_comparison(auth_client, analysis_id, {
        "comparison_type": "categorical_numeric", "group_column": "tier", "value_column": "score"})
    finding = by_type(suggest(auth_client, analysis_id).json())["group_difference"]
    assert finding["evidence_values"]["comparison_basis"] == "ranks"
    assert "rank comparison, not a comparison of means" in finding["explanation"]


def test_real_regrouped_comparison_is_explained_with_before_and_after_counts(auth_client):
    analysis_id = upload(auth_client, three_group_csv())
    saved = post_comparison(auth_client, analysis_id, {
        "comparison_type": "categorical_numeric", "group_column": "tier", "value_column": "score",
        "category_mappings": {"tier": [{"label": "upper", "categories": ["mid", "high"]}]}})

    body = suggest(auth_client, analysis_id).json()

    finding = by_type(body)["regrouping"]
    column = saved["regrouping"]["columns"][0]
    assert finding["evidence_refs"][0]["comparison_id"] == saved["comparison_id"]
    assert finding["visual"]["chart_type"] == "before_after_bar"
    assert finding["visual"]["data"] == {"before": column["before"], "after": column["after"]}
    assert finding["evidence_values"]["mapping"] == saved["regrouping"]["mappings"]["tier"]
    assert "regrouping" not in body["unavailable_analyses"]
    assert "different question" in finding["explanation"]
    assert "do not show that it is more valid" in finding["explanation"]
    assert any("method changed" in w for w in finding["warnings"])
    assert by_type(body)["group_difference"]["evidence_values"]["method_key"] == "welch_t_test"


def test_real_identifier_warning_reaches_the_comparison_finding(auth_client):
    csv = "uid,grp,score\n" + "".join(f"u{i},{'a' if i % 2 else 'b'},{i % 7}\n" for i in range(30))
    analysis_id = auth_client.post("/api/analyze", files={"file": ("d.csv", csv, "text/csv")}).json()["analysis_id"]
    post_comparison(auth_client, analysis_id, {
        "comparison_type": "categorical_numeric", "group_column": "uid", "value_column": "score"})
    body = suggest(auth_client, analysis_id).json()
    assert any(
        "may be an identifier" in warning
        for item in body["suggestions"] for warning in item["warnings"]
    )


# --- reports saved before newer sections existed ---------------------------------------------


def make_report_older(analysis_id, keep):
    """Rewrite the stored report so it only has the given top-level sections."""
    from backend.database.connection import session_scope
    from backend.models.records import AnalysisReport

    with session_scope(app.state.engine) as session:
        record = session.get(AnalysisReport, analysis_id)
        record.report = {key: value for key, value in record.report.items() if key in keep}


OLDEST_SECTIONS = {"schema_version", "dataset_id", "analysis_id", "filename", "status", "started_at",
                   "completed_at", "dataset", "summary", "parsing_options", "missing_values", "outliers",
                   "validation", "diagnostics", "findings"}


def test_a_report_saved_before_profiles_duplicates_and_correlation_still_works(auth_client):
    analysis_id = upload(auth_client)
    current = suggest(auth_client, analysis_id).json()
    assert "duplicates" in by_type(current)

    make_report_older(analysis_id, OLDEST_SECTIONS)
    older = suggest(auth_client, analysis_id)

    assert older.status_code == 200
    body = older.json()
    SuggestionResponse(**body)
    types = by_type(body)
    assert "missing_values" in types and "duplicates" not in types
    assert types["missing_values"]["evidence_values"]["missing_count"] == 10
    assert all(item["visual"]["chart_type"] for item in body["suggestions"])


def test_an_older_report_with_a_saved_comparison_still_explains_it(auth_client):
    analysis_id = upload(auth_client)
    compare(auth_client, analysis_id, "group", "score")
    make_report_older(analysis_id, OLDEST_SECTIONS)

    body = suggest(auth_client, analysis_id).json()

    assert "group_difference" in by_type(body)
    assert body["comparison_ids_used"]


def test_a_report_with_no_optional_sections_at_all_gives_an_empty_valid_response(auth_client):
    analysis_id = upload(auth_client, clean_csv())
    make_report_older(analysis_id, {"analysis_id", "dataset", "status", "filename"})

    response = suggest(auth_client, analysis_id)

    assert response.status_code == 200
    assert response.json()["suggestions"] == [] and response.json()["total_findings"] == 0
