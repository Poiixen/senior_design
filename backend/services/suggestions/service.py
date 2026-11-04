"""Build the suggestions response for one saved report."""

from typing import Optional

from backend.database import repository
from backend.database.connection import session_scope
from backend.models.suggestions import Suggestion, SuggestionRequest, SuggestionResponse
from backend.services.suggestions import ai_wording
from backend.services.suggestions.evidence import load_evidence
from backend.services.suggestions.fallback import _with_warnings, describe
from backend.services.suggestions.ranking import priority_band, rank
from backend.services.suggestions.rules import collect_candidates


def _suggestion(candidate, score: float) -> dict:
    parts = describe(candidate)
    percent = max(0, min(100, round(100 * score)))
    return {
        "title": parts["title"],
        "affected_columns": [str(column) for column in candidate.columns if column],
        "explanation": parts["explanation"],
        "evidence": parts["evidence"],
        "next_steps": parts["next_steps"],
        "finding_id": candidate.finding_id,
        "finding_type": candidate.finding_type,
        "priority": priority_band(score),
        "priority_percent": percent,
        "priority_reason": candidate.reason,
        "evidence_refs": [ref.model_dump() for ref in candidate.refs],
        "evidence_values": candidate.values,
        "warnings": candidate.warnings,
        "exploratory": candidate.exploratory,
        "visual": candidate.visual.model_dump(),
    }


def _ai_items(suggestions: list) -> list:
    """Compact aggregates only: no rows, no cell values."""
    return [
        {
            "finding_id": s["finding_id"],
            "finding_type": s["finding_type"],
            "columns": s["affected_columns"],
            "evidence": s["evidence"],
            "evidence_values": s["evidence_values"],
            "warnings": s["warnings"],
            "exploratory": s["exploratory"],
            "draft_explanation": s["explanation"],
            "draft_next_steps": s["next_steps"],
        }
        for s in suggestions
    ]


def _apply_ai(suggestions: list, candidates: dict, complete) -> bool:
    reworded = ai_wording.reword(_ai_items(suggestions), complete)
    if reworded is None:
        return False
    for suggestion in suggestions:
        new = reworded[suggestion["finding_id"]]
        suggestion["title"] = new["title"]
        suggestion["explanation"] = _with_warnings(candidates[suggestion["finding_id"]], new["explanation"])
        suggestion["next_steps"] = new["next_steps"]
    return True


def deterministic_findings(evidence, limit: int) -> tuple:
    """The top ``limit`` findings with their deterministic text, and the total.

    Used by callers that ground their own output in the same findings the
    suggestions endpoint ranks, without asking a model for new wording.
    """
    ranked = rank(collect_candidates(evidence))
    return [_suggestion(candidate, score) for candidate, score in ranked[:limit]], len(ranked)


def generate_suggestions(
    analysis_service,
    analysis_id: int,
    user_id: int,
    request: Optional[SuggestionRequest] = None,
    complete: Optional[ai_wording.Complete] = None,
) -> Optional[dict]:
    """Return the response dict, or None when the user does not own the report.

    Raises InvalidComparisonSelection for a comparison id that does not
    belong to the report.
    """
    request = request or SuggestionRequest()
    with session_scope(analysis_service.engine) as session:
        report = repository.get_analysis_report_for_user(session, analysis_id, user_id)
    if report is None:
        return None

    saved = analysis_service.list_comparisons(analysis_id, user_id)
    evidence = load_evidence(analysis_id, report, saved, request.comparison_ids)
    ranked = rank(collect_candidates(evidence))
    page = ranked[request.offset : request.offset + request.limit]

    suggestions = [_suggestion(candidate, value) for candidate, value in page]
    candidates = {candidate.finding_id: candidate for candidate, _ in page}
    used_ai = _apply_ai(suggestions, candidates, complete) if suggestions else False

    response = SuggestionResponse(
        analysis_id=analysis_id,
        source="ai" if used_ai else "fallback",
        suggestions=[Suggestion(**suggestion) for suggestion in suggestions],
        comparison_ids_used=evidence.comparison_ids,
        evidence_fingerprint=evidence.fingerprint,
        total_findings=len(ranked),
        offset=request.offset,
        has_more=request.offset + request.limit < len(ranked),
        unavailable_analyses=evidence.unavailable,
    )
    return response.model_dump(mode="json")
