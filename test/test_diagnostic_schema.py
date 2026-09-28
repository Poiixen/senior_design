"""Tests for the standardized DiagnosticResult schema (Ticket #11)."""

import pytest
from pydantic import ValidationError

from backend.models.schemas import DiagnosticResult


def test_diagnostic_result_accepts_required_fields_with_optional_defaults():
    result = DiagnosticResult(
        diagnostic="missing_values",
        column="occupation",
        severity="moderate",
        value=5.66,
        message="5.66% of values are missing.",
    )

    assert result.recommendation is None
    assert result.metadata is None


def test_diagnostic_result_supports_dataset_wide_findings():
    result = DiagnosticResult(
        diagnostic="duplicates",
        column=None,
        severity="none",
        value=0.0,
        message="0 of 3 rows are duplicates (0.00%).",
    )

    assert result.column is None


def test_diagnostic_result_requires_severity_and_message():
    with pytest.raises(ValidationError):
        DiagnosticResult(diagnostic="missing_values", column="a", value=1.0)
