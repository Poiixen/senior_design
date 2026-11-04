"""The saved results a follow-up answer may draw on.

Everything here is a compact aggregate from the report, its ranked findings
and its saved comparisons. No dataset rows or cell values are included. Each
item has a ``source_id`` so an answer can cite it; the backend, not the model,
turns those ids back into the source descriptors that are stored and shown.
"""

from dataclasses import dataclass

from backend.services.suggestions.evidence import Evidence
from backend.services.suggestions.service import deterministic_findings

MAX_FINDINGS = 10
MAX_COMPARISONS = 10
MAX_GROUPS = 12

SIGNIFICANCE_THRESHOLD = 0.05

# Keys copied from a saved comparison. Cell tables and anything else are left out.
_COMPARISON_KEYS = (
    "comparison_type",
    "design",
    "selection",
    "status",
    "reason",
    "group_categories",
    "group_totals",
    "percentage_denominator",
    "warnings",
)
_ROW_KEYS = ("total", "included", "excluded")
_GROUP_KEYS = ("label", "count", "mean", "median", "std_dev")
_TEST_KEYS = (
    "status",
    "reason",
    "statistic_name",
    "statistic",
    "degrees_of_freedom",
    "p_value",
    "mean_difference",
    "mean_difference_ci",
    "eta_squared",
    "difference_order",
)
_METHOD_KEYS = ("key", "name", "evaluates")
_ASSOCIATION_KEYS = ("status", "name", "value")


@dataclass(frozen=True)
class Grounding:
    context: dict
    sources: dict  # source_id -> descriptor stored with an answer

    def descriptors(self, source_ids: list) -> list:
        return [self.sources[source_id] for source_id in source_ids]


def _pick(mapping, keys) -> dict:
    mapping = mapping if isinstance(mapping, dict) else {}
    return {key: mapping[key] for key in keys if key in mapping}


def compact_comparison(comparison: dict) -> dict:
    """The aggregates of one saved comparison, without its raw tables."""
    compact = _pick(comparison, _COMPARISON_KEYS)
    compact["comparison_id"] = comparison.get("comparison_id")
    compact["rows"] = _pick(comparison.get("rows"), _ROW_KEYS)
    if isinstance(comparison.get("overall"), dict):
        compact["overall"] = _pick(comparison["overall"], _GROUP_KEYS[1:])
    groups = comparison.get("groups") or []
    compact["groups"] = [_pick(group, _GROUP_KEYS) for group in groups[:MAX_GROUPS]]
    compact["groups_omitted"] = max(0, len(groups) - MAX_GROUPS)
    test = comparison.get("test") or {}
    compact["test"] = {**_pick(test, _TEST_KEYS), "method": _pick(test.get("method"), _METHOD_KEYS)}
    if isinstance(comparison.get("association"), dict):
        compact["association"] = _pick(comparison["association"], _ASSOCIATION_KEYS)
    regrouping = comparison.get("regrouping")
    if regrouping:
        compact["regrouping"] = _pick(
            regrouping, ("applied", "mappings", "original_comparison_id", "method_change")
        )
    return compact


def _comparison_label(comparison: dict) -> str:
    selection = comparison.get("selection") or {}
    columns = [
        selection.get("group_column"),
        selection.get("value_column") or selection.get("outcome_column"),
    ]
    named = " and ".join(str(column) for column in columns if column)
    return f"Comparison {comparison.get('comparison_id')}" + (f": {named}" if named else "")


def build_grounding(evidence: Evidence) -> Grounding:
    """Context for the model plus the descriptors of every citable source."""
    findings, total_findings = deterministic_findings(evidence, MAX_FINDINGS)
    sources: dict = {}
    finding_items = []
    for finding in findings:
        source_id = f"finding:{finding['finding_id']}"
        refs = finding["evidence_refs"]
        method = finding["evidence_values"].get("method_name")
        sources[source_id] = {
            "source_id": source_id,
            "kind": "finding",
            "label": finding["title"],
            "finding_id": finding["finding_id"],
            "comparison_id": next((r["comparison_id"] for r in refs if r.get("comparison_id")), None),
            "method": method,
        }
        finding_items.append(
            {
                "source_id": source_id,
                "finding_type": finding["finding_type"],
                "title": finding["title"],
                "columns": finding["affected_columns"],
                "priority": finding["priority"],
                "priority_reason": finding["priority_reason"],
                "evidence": finding["evidence"],
                "evidence_values": finding["evidence_values"],
                "warnings": finding["warnings"],
                "exploratory": finding["exploratory"],
                "explanation": finding["explanation"],
                "next_steps": finding["next_steps"],
            }
        )

    comparison_items = []
    for comparison in evidence.comparisons[-MAX_COMPARISONS:]:
        source_id = f"comparison:{comparison['comparison_id']}"
        compact = compact_comparison(comparison)
        sources[source_id] = {
            "source_id": source_id,
            "kind": "comparison",
            "label": _comparison_label(comparison),
            "comparison_id": comparison["comparison_id"],
            "method": compact["test"]["method"].get("name"),
        }
        comparison_items.append({"source_id": source_id, **compact})

    overview_id = "report:overview"
    sources[overview_id] = {
        "source_id": overview_id,
        "kind": "report",
        "label": "Saved report overview",
    }
    context = {
        "significance_threshold": SIGNIFICANCE_THRESHOLD,
        "report": {
            "source_id": overview_id,
            **_pick(evidence.report.get("dataset"), ("rows", "columns")),
        },
        # Analyses with no saved result: nothing may be implied about them.
        "analyses_not_available": evidence.unavailable,
        "findings": finding_items,
        "findings_shown": len(finding_items),
        "findings_total": total_findings,
        "comparisons": comparison_items,
    }
    return Grounding(context=context, sources=sources)
