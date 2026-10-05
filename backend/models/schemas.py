"""Standardized diagnostic result and analysis report schemas.

``DiagnosticResult`` is the common contract diagnostics return before
persistence, so future statistical and fairness checks (KS tests, ANOVA,
regression, fairness metrics) plug into the same shape as the existing
missing-value and duplicate checks. ``AnalysisReport`` is the complete,
JSON-safe snapshot shared by the service, the API and saved-report retrieval.
"""

from datetime import datetime
from math import isfinite
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

REPORT_SCHEMA_VERSION = 1

# Findings with these severities describe the dataset rather than flag a problem.
NON_ISSUE_SEVERITIES = {"none", "info"}


def finite_or_none(value: Any) -> Any:
    """Replace NaN and +/-inf with None, recursing into dicts and lists."""
    if isinstance(value, float):
        return value if isfinite(value) else None
    if isinstance(value, dict):
        return {key: finite_or_none(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite_or_none(item) for item in value]
    return value


class DiagnosticResult(BaseModel):
    """One finding.

    ``value`` units depend on ``diagnostic``: missing_values, duplicates and
    outliers use percentages on a 0-100 scale; profile findings use the
    column's unique-value count; validation findings carry no value.
    Counts and bounds behind a percentage live in ``metadata``.

    A finding is an *issue* unless its severity is "none" or "info"
    (see ``is_issue``). Non-issue findings are informational results.
    """

    diagnostic: str
    column: Optional[str] = None
    severity: str
    value: Optional[float] = None
    message: str
    recommendation: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None

    @field_validator("value")
    @classmethod
    def _value_is_finite(cls, value):
        return finite_or_none(value)

    @field_validator("metadata")
    @classmethod
    def _metadata_is_finite(cls, metadata):
        return finite_or_none(metadata)

    @property
    def is_issue(self) -> bool:
        return self.severity not in NON_ISSUE_SEVERITIES


class DatasetProfile(BaseModel):
    rows: int
    columns: int
    numeric_columns: list[str] = Field(default_factory=list)
    categorical_columns: list[str] = Field(default_factory=list)
    column_details: list[dict[str, Any]] = Field(default_factory=list)


class ReportSummary(BaseModel):
    """Issue counts. Informational findings are not counted."""

    issues_detected: int = 0
    issues_by_severity: dict[str, int] = Field(default_factory=dict)
    issues_by_diagnostic: dict[str, int] = Field(default_factory=dict)


class AnalysisReport(BaseModel):
    """Complete saved snapshot of one analysis run.

    ``profile`` is empty (no columns listed) when structural validation
    failed, in which case ``findings`` holds only validation findings.
    Datetimes are naive UTC.
    """

    schema_version: int = REPORT_SCHEMA_VERSION
    dataset_id: int
    analysis_id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    valid: bool
    parsing_options: dict[str, Any] = Field(default_factory=dict)
    profile: DatasetProfile
    summary: ReportSummary
    findings: list[DiagnosticResult]

    @classmethod
    def build(
        cls,
        *,
        dataset_id: int,
        analysis_id: int,
        status: str,
        started_at: datetime,
        completed_at: Optional[datetime],
        valid: bool,
        parsing_options: dict[str, Any],
        profile: DatasetProfile,
        findings: list[DiagnosticResult],
    ) -> "AnalysisReport":
        issues = [finding for finding in findings if finding.is_issue]
        summary = ReportSummary(issues_detected=len(issues))
        for finding in issues:
            summary.issues_by_severity[finding.severity] = (
                summary.issues_by_severity.get(finding.severity, 0) + 1
            )
            summary.issues_by_diagnostic[finding.diagnostic] = (
                summary.issues_by_diagnostic.get(finding.diagnostic, 0) + 1
            )
        return cls(
            dataset_id=dataset_id,
            analysis_id=analysis_id,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            valid=valid,
            parsing_options=finite_or_none(parsing_options),
            profile=profile,
            summary=summary,
            findings=findings,
        )

    def to_json(self) -> str:
        """Serialize as strict JSON (non-finite numbers are already null)."""
        return self.model_dump_json()
