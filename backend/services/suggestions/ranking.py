"""Scoring, deduplication and ordering of candidate findings.

score = reliability * (SIZE_WEIGHT * size + COVERAGE_WEIGHT * coverage)

``size`` is how large the observed pattern is, ``coverage`` the share of
observations it affects and ``reliability`` how much the evidence can be
trusted. All three are 0-1 values set by the rules. p-values never enter the
score directly; a non-significant comparison only has its size halved.
Documented in docs/suggestions-ranking.md.
"""

from backend.services.suggestions.rules import Candidate

SIZE_WEIGHT = 0.6
COVERAGE_WEIGHT = 0.4
HIGH_THRESHOLD = 0.75
MEDIUM_THRESHOLD = 0.45


def score(candidate: Candidate) -> float:
    return candidate.reliability * (
        SIZE_WEIGHT * candidate.size + COVERAGE_WEIGHT * candidate.coverage
    )


def priority_band(value: float) -> str:
    if value >= HIGH_THRESHOLD:
        return "high"
    if value >= MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _comparison_id(candidate: Candidate) -> int:
    for ref in candidate.refs:
        if ref.comparison_id is not None:
            return ref.comparison_id
    return -1


def _merge_refs(kept: Candidate, other: Candidate) -> None:
    known = {(ref.result_type, ref.comparison_id, ref.column) for ref in kept.refs}
    for ref in other.refs:
        if (ref.result_type, ref.comparison_id, ref.column) not in known:
            kept.refs.append(ref)


def deduplicate(candidates: list) -> list:
    """Collapse findings that describe the same pattern.

    Findings on the same column's distribution (outliers, skew) keep the
    higher-scoring one. Repeats of the same saved comparison selection keep
    the most recent comparison. The dropped finding's references stay on the
    kept one so its evidence remains traceable.
    """
    by_id = {}
    for candidate in candidates:
        by_id.setdefault(candidate.finding_id, candidate)

    kept = []
    groups = {}
    for candidate in by_id.values():
        if candidate.overlap_key is None:
            kept.append(candidate)
        else:
            groups.setdefault(candidate.overlap_key, []).append(candidate)

    for key, members in groups.items():
        if key[0] == "comparison":
            winner = max(members, key=_comparison_id)
        else:
            winner = max(members, key=lambda member: (score(member), member.finding_id))
        for other in members:
            if other is not winner:
                _merge_refs(winner, other)
                winner.values.setdefault("also_covers", []).append(other.finding_type)
        kept.append(winner)
    return kept


def rank(candidates: list) -> list:
    """Return ``(candidate, score)`` pairs, best first, ties broken by id."""
    scored = [(candidate, score(candidate)) for candidate in deduplicate(candidates)]
    scored.sort(key=lambda pair: (-round(pair[1], 9), pair[0].finding_id))
    return scored
