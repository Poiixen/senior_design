"""Metadata persistence operations with caller-owned transactions.

Pass a Session (normally from session_scope). Writes flush to obtain IDs and
check constraints, but never commit. Queries return models, not SQL rows.
"""

from datetime import datetime
from math import isfinite
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    Analysis,
    AnalysisReport,
    Comparison,
    Dataset,
    DiagnosticResult,
    User,
)


def create_user(session: Session, *, email: str, password_hash: str) -> User:
    """Store a user. Emails are unique; a duplicate raises IntegrityError."""
    user = User(email=email, password_hash=password_hash)
    session.add(user)
    session.flush()
    return user


def get_user(session: Session, user_id: int) -> Optional[User]:
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    return session.scalars(select(User).where(User.email == email)).first()


def create_dataset(
    session: Session,
    *,
    name: str,
    row_count: int,
    column_count: int,
    source: Optional[str] = None,
    file_name: Optional[str] = None,
    user_id: Optional[int] = None,
) -> Dataset:
    """Store dataset metadata. Counts must be nonnegative integers."""
    for label, count in (("row_count", row_count), ("column_count", column_count)):
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"{label} must be a nonnegative integer")
    dataset = Dataset(
        user_id=user_id,
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


def save_analysis_report(session: Session, analysis_id: int, report: dict) -> AnalysisReport:
    """Save the complete structured report in the analysis transaction."""
    record = AnalysisReport(analysis_id=analysis_id, report=report)
    session.add(record)
    session.flush()
    return record


def get_analysis_report(session: Session, analysis_id: int) -> Optional[dict]:
    record = session.get(AnalysisReport, analysis_id)
    return record.report if record is not None else None


def get_analysis_for_user(
    session: Session, analysis_id: int, user_id: int
) -> Optional[Analysis]:
    """Return the analysis only when its dataset belongs to the user."""
    return session.scalars(
        select(Analysis)
        .join(Dataset, Analysis.dataset_id == Dataset.id)
        .where(Analysis.id == analysis_id, Dataset.user_id == user_id)
    ).first()


def get_analysis_report_for_user(
    session: Session, analysis_id: int, user_id: int
) -> Optional[dict]:
    """Return the saved report only when the user owns it, else None."""
    record = session.scalars(
        select(AnalysisReport)
        .join(Analysis, AnalysisReport.analysis_id == Analysis.id)
        .join(Dataset, Analysis.dataset_id == Dataset.id)
        .where(AnalysisReport.analysis_id == analysis_id, Dataset.user_id == user_id)
    ).first()
    return record.report if record is not None else None


def list_analysis_reports_for_user(session: Session, user_id: int) -> list[dict]:
    """Return the user's saved report snapshots newest first."""
    records = session.scalars(
        select(AnalysisReport)
        .join(Analysis, AnalysisReport.analysis_id == Analysis.id)
        .join(Dataset, Analysis.dataset_id == Dataset.id)
        .where(Dataset.user_id == user_id)
        .order_by(AnalysisReport.analysis_id.desc())
    )
    return [record.report for record in records]


def list_analysis_reports(session: Session) -> list[dict]:
    """Return saved report snapshots newest first."""
    records = session.scalars(
        select(AnalysisReport).order_by(AnalysisReport.analysis_id.desc())
    )
    return [record.report for record in records]


def save_comparison(
    session: Session, *, analysis_id: int, comparison_type: str, result: dict
) -> Comparison:
    """Save a JSON-safe comparison result for an analysis."""
    comparison = Comparison(
        analysis_id=analysis_id, comparison_type=comparison_type, result=result
    )
    session.add(comparison)
    session.flush()
    return comparison


def list_comparisons_for_user(
    session: Session, analysis_id: int, user_id: int
) -> list[Comparison]:
    """Return the analysis's comparisons oldest first, if the user owns it."""
    return list(session.scalars(
        select(Comparison)
        .join(Analysis, Comparison.analysis_id == Analysis.id)
        .join(Dataset, Analysis.dataset_id == Dataset.id)
        .where(Comparison.analysis_id == analysis_id, Dataset.user_id == user_id)
        .order_by(Comparison.id)
    ))


def get_comparison_for_user(
    session: Session, analysis_id: int, comparison_id: int, user_id: int
) -> Optional[Comparison]:
    """Return one comparison of the analysis only when the user owns it."""
    return session.scalars(
        select(Comparison)
        .join(Analysis, Comparison.analysis_id == Analysis.id)
        .join(Dataset, Analysis.dataset_id == Dataset.id)
        .where(
            Comparison.id == comparison_id,
            Comparison.analysis_id == analysis_id,
            Dataset.user_id == user_id,
        )
    ).first()
