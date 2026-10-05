"""Metadata persistence operations with caller-owned transactions.

Pass a Session (normally from session_scope). Writes flush to obtain IDs and
check constraints, but never commit. Queries return models, not SQL rows.
"""

from datetime import datetime
from math import isfinite
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Analysis, Dataset, DiagnosticResult, ReportRecord


def create_dataset(
    session: Session,
    *,
    name: str,
    row_count: int,
    column_count: int,
    source: Optional[str] = None,
    file_name: Optional[str] = None,
) -> Dataset:
    """Store dataset metadata. Counts must be nonnegative integers."""
    for label, count in (("row_count", row_count), ("column_count", column_count)):
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"{label} must be a nonnegative integer")
    dataset = Dataset(
        name=name,
        source=source,
        file_name=file_name,
        row_count=row_count,
        column_count=column_count,
    )
    session.add(dataset)
    session.flush()
    return dataset


def get_dataset(session: Session, dataset_id: int) -> Optional[Dataset]:
    """Return a dataset, or None when the ID does not exist."""
    return session.get(Dataset, dataset_id)


def list_datasets(session: Session) -> list[Dataset]:
    return list(session.scalars(select(Dataset).order_by(Dataset.id)))


def create_analysis(session: Session, dataset_id: int) -> Analysis:
    """Start a run for an existing dataset; invalid parents fail the FK check."""
    analysis = Analysis(dataset_id=dataset_id, status="running")
    session.add(analysis)
    session.flush()
    return analysis


def get_analysis(session: Session, analysis_id: int) -> Optional[Analysis]:
    return session.get(Analysis, analysis_id)


def list_analyses(session: Session, dataset_id: int) -> list[Analysis]:
    return list(session.scalars(
        select(Analysis).where(Analysis.dataset_id == dataset_id).order_by(Analysis.id)
    ))


def finish_analysis(
    session: Session, analysis_id: int, *, status: str = "completed"
) -> Analysis:
    """Finish a running analysis as completed or failed, stamping UTC time.

    Raise ValueError for unknown IDs, unsupported statuses, or finished runs.
    """
    if status not in ("completed", "failed"):
        raise ValueError("Finished status must be 'completed' or 'failed'")
    analysis = get_analysis(session, analysis_id)
    if analysis is None:
        raise ValueError(f"Analysis {analysis_id} does not exist")
    if analysis.status != "running":
        raise ValueError(f"Analysis {analysis_id} is already finished")
    analysis.status = status
    analysis.completed_at = datetime.utcnow()
    session.flush()
    return analysis


def save_report(
    session: Session, analysis_id: int, *, schema_version: int, report_json: str
) -> ReportRecord:
    """Store the report snapshot for an analysis in the caller's transaction."""
    if get_analysis(session, analysis_id) is None:
        raise ValueError(f"Analysis {analysis_id} does not exist")
    record = ReportRecord(
        analysis_id=analysis_id,
        schema_version=schema_version,
        report_json=report_json,
    )
    session.add(record)
    session.flush()
    return record


def get_report(session: Session, analysis_id: int) -> Optional[ReportRecord]:
    """Return the saved report snapshot, or None when the run has none."""
    return session.get(ReportRecord, analysis_id)


def save_diagnostic_result(
    session: Session,
    *,
    analysis_id: int,
    diagnostic_type: str,
    column_name: Optional[str] = None,
    severity: str = "info",
    value: Optional[float] = None,
    message: str = "",
) -> DiagnosticResult:
    """Save a scalar metric. None column_name denotes a dataset-wide result.

    Values must be finite numbers or None. Units belong to the diagnostic's
    documented contract; severity and diagnostic type are extensible strings.
    """
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Diagnostic value must be a finite number or None")
        if not isfinite(value):
            raise ValueError("Diagnostic value must be a finite number or None")
    result = DiagnosticResult(
        analysis_id=analysis_id,
        diagnostic_type=diagnostic_type,
        column_name=column_name,
        severity=severity,
        value=value,
        message=message,
    )
    session.add(result)
    session.flush()
    return result


def get_diagnostic_result(
    session: Session, result_id: int
) -> Optional[DiagnosticResult]:
    return session.get(DiagnosticResult, result_id)


def list_diagnostic_results(
    session: Session, analysis_id: int
) -> list[DiagnosticResult]:
    return list(session.scalars(
        select(DiagnosticResult)
        .where(DiagnosticResult.analysis_id == analysis_id)
        .order_by(DiagnosticResult.id)
    ))
