"""Collect the saved results one suggestions request may draw on."""

import hashlib
import json
from dataclasses import dataclass
from typing import Optional


class InvalidComparisonSelection(ValueError):
    """A requested comparison does not belong to the report."""


@dataclass(frozen=True)
class Evidence:
    analysis_id: int
    report: dict
    comparisons: list
    unavailable: list
    fingerprint: str

    @property
    def comparison_ids(self) -> list:
        return [comparison["comparison_id"] for comparison in self.comparisons]

    @property
    def total_rows(self) -> int:
        return int((self.report.get("dataset") or {}).get("rows") or 0)

    def profile(self, column: str) -> Optional[dict]:
        for entry in self.report.get("column_profiles") or []:
            if entry.get("name") == column:
                return entry
        return None


def _method_key(comparison: dict) -> str:
    return str(((comparison.get("test") or {}).get("method") or {}).get("key") or "")


def _unavailable_analyses(report: dict, comparisons: list) -> list:
    """Analyses with no saved result, so no explanation may imply they ran."""
    missing = []
    if not any("anova" in _method_key(comparison) for comparison in comparisons):
        missing.append("anova")
    profiles = report.get("column_profiles") or []
    if not any(
        (entry.get("distribution_shape") or {}).get("skewness") is not None
        for entry in profiles
        if entry.get("category") == "numeric"
    ):
        missing.append("distribution")
    if not any(comparison.get("regrouping") for comparison in comparisons):
        missing.append("regrouping")
    return missing


def fingerprint(analysis_id: int, comparisons: list) -> str:
    material = json.dumps(
        [analysis_id, [[c["comparison_id"], c.get("created_at")] for c in comparisons]]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def load_evidence(
    analysis_id: int,
    report: dict,
    saved_comparisons: list,
    requested_ids: Optional[list] = None,
) -> Evidence:
    """Select the report's comparisons; reject ids from any other report.

    ``saved_comparisons`` must already be limited to the requesting user.
    Older reports may lack any section, so every read is optional.
    """
    owned = {
        comparison["comparison_id"]: comparison
        for comparison in saved_comparisons
        if comparison.get("analysis_id") == analysis_id
    }
    if requested_ids is None:
        selected = [owned[key] for key in sorted(owned)]
    else:
        unknown = sorted(set(requested_ids) - set(owned))
        if unknown:
            raise InvalidComparisonSelection(
                f"Comparison {unknown[0]} does not belong to this report."
            )
        selected = [owned[key] for key in sorted(set(requested_ids))]
    return Evidence(
        analysis_id=analysis_id,
        report=report,
        comparisons=selected,
        unavailable=_unavailable_analyses(report, selected),
        fingerprint=fingerprint(analysis_id, selected),
    )
