"""Request and response models for POST /api/reports/{analysis_id}/suggestions.

The five fields the frontend already requires (``title``, ``affected_columns``,
``explanation``, ``evidence``, ``next_steps``) keep their meaning. Every other
field is additive and has a default, so older clients keep working.

Evidence values, ranking and chart data are computed by the backend from saved
results. Optional AI wording may only replace ``title``, ``explanation`` and
``next_steps``.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from backend.models.schemas import _FiniteModel

DEFAULT_LIMIT = 5
MAX_LIMIT = 20

FindingType = Literal[
    "missing_values",
    "duplicates",
    "outliers",
    "correlation",
    "group_difference",
    "categorical_association",
    "skewed_distribution",
    "unavailable_test",
    "small_groups",
    "regrouping",
]

Priority = Literal["high", "medium", "low"]

ChartType = Literal[
    "bar",
    "histogram",
    "box_plot",
    "grouped_box",
    "grouped_percentage_bar",
    "contingency_heatmap",
    "correlation_pair",
    "before_after_bar",
    "evidence_table",
]


class SuggestionRequest(BaseModel):
    """Optional body. An empty body uses every saved comparison of the report."""

    comparison_ids: Optional[list[int]] = None
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    offset: int = Field(0, ge=0)


class EvidenceRef(BaseModel):
    """Points at the saved result a value came from."""

    result_type: Literal[
        "missing_values",
        "duplicates",
        "outliers",
        "correlation",
        "column_profile",
        "comparison",
    ]
    analysis_id: int
    comparison_id: Optional[int] = None
    column: Optional[str] = None


class VisualSpec(_FiniteModel):
    """Chart description the frontend renders. All values are saved aggregates.

    ``chart_type`` "evidence_table" is the fallback when the saved evidence
    cannot support a chart; ``fallback_reason`` then says why and ``data``
    holds ``{"rows": [{"label": str, "value": ...}]}``.
    """

    chart_type: ChartType
    title: str
    source: EvidenceRef
    data: dict[str, Any] = Field(default_factory=dict)
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    units: Optional[str] = None
    percent_denominator: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    unavailable_fields: list[str] = Field(default_factory=list)
    fallback_reason: Optional[str] = None


class Suggestion(_FiniteModel):
    # Required by the existing frontend contract.
    title: str
    affected_columns: list[str]
    explanation: str
    evidence: list[str]
    next_steps: list[str]
    # Additive fields.
    finding_id: str
    finding_type: FindingType
    priority: Priority
    priority_percent: int = Field(ge=0, le=100)
    priority_reason: str
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    evidence_values: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    exploratory: bool = False
    visual: VisualSpec


class SuggestionResponse(BaseModel):
    analysis_id: int
    source: Literal["ai", "fallback"]
    suggestions: list[Suggestion]
    # Identifies the exact evidence used. The frontend compares it with the
    # report's current comparison list to detect outdated output.
    comparison_ids_used: list[int] = Field(default_factory=list)
    evidence_fingerprint: str
    total_findings: int
    offset: int = 0
    has_more: bool = False
    # Analyses that were not available, so nothing is implied about them.
    unavailable_analyses: list[str] = Field(default_factory=list)
