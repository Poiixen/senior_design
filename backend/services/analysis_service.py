"""Run DataFrame diagnostics and persist only metadata and summary findings."""

from typing import Any, Optional

from pandas import DataFrame
from sqlalchemy.engine import Engine

from backend.database import repository
from backend.database.connection import session_scope
from backend.diagnostics.generic_dataset_profiler import profile_dataset
from backend.diagnostics.iqr_outlier_detection import detect_numeric_outliers
from backend.diagnostics.validate_dataset import validate_dataset
from backend.models import Analysis, Dataset, DiagnosticResult
from backend.models.schemas import (
    REPORT_SCHEMA_VERSION,
    AnalysisReport,
    DatasetProfile,
)
from backend.models.schemas import DiagnosticResult as DiagnosticResultSchema


def _dataset_profile(df: DataFrame, profile: Optional[dict]) -> DatasetProfile:
    """Summarize the dataset; column lists stay empty when no profile was run."""
    rows, columns = len(df), len(df.columns)
    if profile is None:
        return DatasetProfile(rows=rows, columns=columns)
    return DatasetProfile(
        rows=rows,
        columns=columns,
        numeric_columns=[str(name) for name in profile["numeric_columns"]],
        categorical_columns=[str(name) for name in profile["categorical_columns"]],
        column_details=[
            {**detail, "name": str(detail["name"])}
            for detail in profile["column_details"]
        ],
    )


def _validation_results(validation: dict) -> list[DiagnosticResultSchema]:
    errors = [
        DiagnosticResultSchema(
            diagnostic="validation", severity="error", message=message
        )
        for message in validation["errors"]
    ]
    warnings = [
        DiagnosticResultSchema(
            diagnostic="validation", severity="warning", message=message
        )
        for message in validation["warnings"]
    ]
    return errors + warnings


def _profile_results(profile: dict) -> list[DiagnosticResultSchema]:
    return [
        DiagnosticResultSchema(
            diagnostic="profile",
            column=str(detail["name"]),
            severity="info",
            value=float(detail["unique_values"]),
            message=(
                f"{detail['category'].capitalize()} column ({detail['dtype']}) "
                f"with {detail['unique_values']} unique values."
            ),
            metadata={
                "dtype": detail["dtype"],
                "category": detail["category"],
                "unique_values": int(detail["unique_values"]),
            },
        )
        for detail in profile["column_details"]
    ]


def _missing_value_result(row: dict, total_rows: int) -> DiagnosticResultSchema:
    missing_count = int(row["missing_count"])
    missing_percentage = float(row["missing_percentage"])
    return DiagnosticResultSchema(
        diagnostic="missing_values",
        column=str(row["column_name"]),
        severity=row["severity"],
        value=missing_percentage,
        message=(
            f"{missing_count} of {total_rows} rows have missing "
            f"values ({missing_percentage:.2f}%)."
        ),
        recommendation=(
            "Consider imputing or dropping this column."
            if missing_count > 0
            else None
        ),
        metadata={"missing_count": missing_count, "total_rows": total_rows},
    )


def _duplicate_result(raw: dict, total_rows: int) -> DiagnosticResultSchema:
    duplicate_count = int(raw["duplicate_count"])
    duplicate_percentage = float(raw["duplicate_percentage"])
    return DiagnosticResultSchema(
        diagnostic="duplicates",
        column=None,
        severity="warning" if duplicate_count > 0 else "none",
        value=duplicate_percentage,
        message=(
            f"{duplicate_count} of {total_rows} rows are duplicates "
            f"({duplicate_percentage:.2f}%)."
        ),
        recommendation=(
            "Review and remove duplicate rows if they are unintended."
            if duplicate_count > 0
            else None
        ),
        metadata={"duplicate_count": duplicate_count, "total_rows": total_rows},
    )


def _outlier_result(raw: dict) -> DiagnosticResultSchema:
    outlier_count = int(raw["outlier_count"])
    outlier_percentage = float(raw["outlier_percentage"])
    return DiagnosticResultSchema(
        diagnostic="outliers",
        column=str(raw["column_name"]),
        severity="warning" if outlier_count > 0 else "none",
        value=outlier_percentage,
        message=(
            f"{outlier_count} values fall outside the IQR bounds "
            f"[{raw['lower_bound']:.4g}, {raw['upper_bound']:.4g}] "
            f"({outlier_percentage:.2f}% of non-missing values)."
        ),
        recommendation=(
            "Check these values for data-entry or measurement errors."
            if outlier_count > 0
            else None
        ),
        metadata={
            "outlier_count": outlier_count,
            "lower_bound": float(raw["lower_bound"]),
            "upper_bound": float(raw["upper_bound"]),
        },
    )


class AnalysisService:
    """Coordinate pure diagnostics with the repository's transactions.

    The caller initializes the database before constructing this service.
    DataFrames remain in memory; only dimensions and diagnostic summaries
    are written to the database.
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    def register_dataset(
        self,
        df: DataFrame,
        *,
        name: str,
        source: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> Dataset:
        """Save dataset metadata and dimensions without storing raw rows."""
        with session_scope(self.engine) as session:
            dataset = repository.create_dataset(
                session,
                name=name,
                source=source,
                file_name=file_name,
                row_count=len(df),
                column_count=len(df.columns),
            )
        return dataset

    def run_analysis(
        self,
        dataset_id: int,
        df: DataFrame,
        parsing_options: Optional[dict[str, Any]] = None,
    ) -> Analysis:
        """Run diagnostics for a DataFrame corresponding to the dataset.

        Structural validation runs first. A dataset with blocking errors
        records only validation findings (severity ``error``) and completes
        without running downstream diagnostics. Otherwise validation warnings,
        per-column profile summaries (severity ``info``), missing values,
        duplicates and IQR outliers are recorded.

        Finding values are percentages on a 0-100 scale, except profile
        findings, whose value is the column's unique-value count. The caller
        supplies the corresponding DataFrame because raw dataset rows are not
        stored, and may pass the CSV ``parsing_options`` used to load it so the
        report records them. A run is recorded before computation begins. All
        findings, the report snapshot and the completed status commit
        together; failure leaves a failed run without partial findings or a
        report and re-raises the original error.
        """
        with session_scope(self.engine) as session:
            if repository.get_dataset(session, dataset_id) is None:
                raise ValueError(f"Dataset {dataset_id} does not exist")
            analysis = repository.create_analysis(session, dataset_id)
        analysis_id = analysis.id

        try:
            validation = validate_dataset(df)
            results = _validation_results(validation)
            profile = None

            if validation["valid"]:
                total_rows = len(df)
                profile = profile_dataset(df)
                results.extend(_profile_results(profile))
                results.extend(
                    _missing_value_result(row, total_rows)
                    for row in profile["missing_values"]
                )
                results.append(_duplicate_result(profile["duplicates"], total_rows))
                results.extend(
                    _outlier_result(raw) for raw in detect_numeric_outliers(df)
                )

            with session_scope(self.engine) as session:
                for result in results:
                    repository.save_diagnostic_result(
                        session,
                        analysis_id=analysis_id,
                        diagnostic_type=result.diagnostic,
                        column_name=result.column,
                        severity=result.severity,
                        value=result.value,
                        message=result.message,
                    )
                analysis = repository.finish_analysis(session, analysis_id)
                report = AnalysisReport.build(
                    dataset_id=dataset_id,
                    analysis_id=analysis_id,
                    status=analysis.status,
                    started_at=analysis.started_at,
                    completed_at=analysis.completed_at,
                    valid=validation["valid"],
                    parsing_options=parsing_options or {},
                    profile=_dataset_profile(df, profile),
                    findings=results,
                )
                repository.save_report(
                    session,
                    analysis_id,
                    schema_version=REPORT_SCHEMA_VERSION,
                    report_json=report.to_json(),
                )
        except Exception:
            with session_scope(self.engine) as session:
                repository.finish_analysis(session, analysis_id, status="failed")
            raise

        return analysis

    def get_report(self, analysis_id: int) -> Optional[AnalysisReport]:
        """Return the saved report snapshot, or None if the run has none."""
        with session_scope(self.engine) as session:
            record = repository.get_report(session, analysis_id)
            if record is None:
                return None
            return AnalysisReport.model_validate_json(record.report_json)

    def list_findings(self, analysis_id: int) -> list[DiagnosticResult]:
        """Return an analysis's saved findings in the order they were recorded."""
        with session_scope(self.engine) as session:
            return repository.list_diagnostic_results(session, analysis_id)
