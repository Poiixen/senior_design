"""Run DataFrame diagnostics and persist only metadata and summary findings."""

from typing import Optional

from pandas import DataFrame
from sqlalchemy.engine import Engine

from backend.database import repository
from backend.database.connection import session_scope
from backend.diagnostics.duplicate_detection import detect_duplicates
from backend.diagnostics.missing_value_detection import detect_missing_values
from backend.models import Analysis, Dataset
from backend.models.schemas import DiagnosticResult as DiagnosticResultSchema


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

    def run_analysis(self, dataset_id: int, df: DataFrame) -> Analysis:
        """Run diagnostics for a DataFrame corresponding to the dataset.

        Finding values are percentages on a 0–100 scale. The caller supplies
        the corresponding DataFrame because raw dataset rows are not stored.
        A run is recorded before computation begins. All findings and the
        completed status commit together; failure leaves a failed run without
        partial findings and re-raises the original error.
        """
        with session_scope(self.engine) as session:
            if repository.get_dataset(session, dataset_id) is None:
                raise ValueError(f"Dataset {dataset_id} does not exist")
            analysis = repository.create_analysis(session, dataset_id)
        analysis_id = analysis.id

        try:
            missing_raw = detect_missing_values(df)
            duplicate_raw = detect_duplicates(df)
            total_rows = len(df)

            missing_results = [
                _missing_value_result(row, total_rows) for row in missing_raw
            ]
            duplicate_result = _duplicate_result(duplicate_raw, total_rows)

            with session_scope(self.engine) as session:
                for result in missing_results:
                    repository.save_diagnostic_result(
                        session,
                        analysis_id=analysis_id,
                        diagnostic_type=result.diagnostic,
                        column_name=result.column,
                        severity=result.severity,
                        value=result.value,
                        message=result.message,
                    )

                repository.save_diagnostic_result(
                    session,
                    analysis_id=analysis_id,
                    diagnostic_type=duplicate_result.diagnostic,
                    column_name=duplicate_result.column,
                    severity=duplicate_result.severity,
                    value=duplicate_result.value,
                    message=duplicate_result.message,
                )
                analysis = repository.finish_analysis(session, analysis_id)
        except Exception:
            with session_scope(self.engine) as session:
                repository.finish_analysis(session, analysis_id, status="failed")
            raise

        return analysis
