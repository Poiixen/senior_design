"""Standardized diagnostic result schema shared across all diagnostics.

This is the common contract diagnostics return before persistence, so future
statistical and fairness checks (KS tests, ANOVA, regression, fairness metrics)
plug into the same shape as the existing missing-value and duplicate checks.
"""

from typing import Any, Optional

from pydantic import BaseModel


class DiagnosticResult(BaseModel):
    diagnostic: str
    column: Optional[str] = None
    severity: str
    value: Optional[float] = None
    message: str
    recommendation: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
