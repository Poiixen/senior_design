
"""Check required columns, expected types, and nullability."""

import math
import numbers

import pandas as pd

from backend.models.schemas import DiagnosticResult
from backend.models.validation_rules import DatasetValidationRules


def _matches_type(value, expected_type: str) -> bool:
    """Check a non-missing value without converting it."""
    if isinstance(value, (bool, str, bytes)):
        return expected_type == "string" and isinstance(value, str)

    if expected_type == "string":
        return isinstance(value, str)

    if expected_type == "integer":
        return isinstance(value, numbers.Integral) or (
            isinstance(value, numbers.Real)
            and math.isfinite(value)
            and float(value).is_integer()
        )

    if expected_type == "number":
        return (
            isinstance(value, numbers.Real)
            and math.isfinite(value)
        )

    return False


def validate_column_rules(
    df: pd.DataFrame,
    rules: DatasetValidationRules,
) -> list[DiagnosticResult]:
    """Return violations without modifying the dataset."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame")

    if not isinstance(rules, DatasetValidationRules):
        raise TypeError("rules must be a DatasetValidationRules instance")

    if not df.columns.is_unique:
        raise ValueError("Column names must be unique")

    findings = []

    for column_name, rule in rules.columns.items():
        # A missing optional column is not a violation.
        if column_name not in df.columns:
            if rule.required:
                findings.append(
                    DiagnosticResult(
                        diagnostic="required_column",
                        column=column_name,
                        severity="error",
                        value=1.0,
                        message=f"Required column '{column_name}' is missing.",
                        metadata={
                            "violation_count": 1,
                            "missing_column_count": 1,
                        },
                    )
                )
            continue

        column = df[column_name]

        # Nullability and type checking are independent.
        missing = column.isna()
        missing_count = int(missing.sum())

        if not rule.nullable and missing_count > 0:
            findings.append(
                DiagnosticResult(
                    diagnostic="nullability",
                    column=column_name,
                    severity="error",
                    value=float(missing_count),
                    message=(
                        f"Column '{column_name}' contains "
                        f"{missing_count} missing values."
                    ),
                    metadata={
                        "violation_count": missing_count,
                        "missing_value_count": missing_count,
                        "total_rows": len(df),
                    },
                )
            )

        # Do not count missing cells as type errors.
        non_missing = column[~missing]
        invalid_count = sum(
            not _matches_type(value, rule.type)
            for value in non_missing
        )

        if invalid_count > 0:
            findings.append(
                DiagnosticResult(
                    diagnostic="column_type",
                    column=column_name,
                    severity="error",
                    value=float(invalid_count),
                    message=(
                        f"Column '{column_name}' has {invalid_count} "
                        f"values incompatible with '{rule.type}'."
                    ),
                    metadata={
                        "violation_count": invalid_count,
                        "expected_type": rule.type,
                        "checked_count": len(non_missing),
                        "total_rows": len(df),
                    },
                )
            )

    return findings
