"""Standardized diagnostic result and analysis report schemas.

``DiagnosticResult`` is the common contract diagnostics return before
persistence, so future statistical and fairness checks (KS tests, ANOVA,
regression, fairness metrics) plug into the same shape as the existing
missing-value and duplicate checks. ``AnalysisReport`` is the complete,
JSON-safe snapshot shared by the service, the API and saved-report retrieval.
Its top-level fields are the contract the frontend reads; ``schema_version``,
``dataset_id`` and ``findings`` are additive.
"""

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


class _FiniteModel(BaseModel):
    """Base model whose fields never hold NaN or infinity (they become null)."""

    @field_validator("*")
    @classmethod
    def _finite(cls, value):
        return finite_or_none(value)


class DiagnosticResult(_FiniteModel):
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

    @property
    def is_issue(self) -> bool:
        return self.severity not in NON_ISSUE_SEVERITIES


class ParsingOptions(BaseModel):
    delimiter: str = ","
    has_header: bool = True
    missing_values: list[str] = Field(default_factory=list)


class ReportDataset(BaseModel):
    rows: int
    columns: int


class ReportSummary(BaseModel):
    issues_detected: int = 0
    numeric_columns: int = 0
    categorical_columns: int = 0
    duplicate_rows: int = 0
    missing_columns: int = 0
    outlier_columns: int = 0


class MissingValueResult(_FiniteModel):
    column_name: str
    missing_count: int
    missing_percentage: Optional[float] = None
    severity: str


class OutlierResult(_FiniteModel):
    column_name: str
    outlier_count: int
    outlier_percentage: Optional[float] = None
    q1: Optional[float] = None
    q3: Optional[float] = None
    iqr: Optional[float] = None
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None


class ValidationResult(BaseModel):
    valid: bool
    rows: int = 0
    columns: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisReport(_FiniteModel):
    """Complete saved snapshot of one analysis run.

    When structural validation fails, ``missing_values``, ``outliers`` and
    ``findings`` hold only what could be computed (validation findings) and
    the column counts in ``summary`` are zero. Timestamps are UTC ISO-8601
    strings ending in ``Z``.
    """

    schema_version: int = REPORT_SCHEMA_VERSION
    dataset_id: int
    analysis_id: int
    filename: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    dataset: ReportDataset
    summary: ReportSummary
    parsing_options: ParsingOptions
    missing_values: list[MissingValueResult]
    outliers: list[OutlierResult]
    validation: ValidationResult
    diagnostics: list[dict[str, Any]]
    findings: list[DiagnosticResult]
