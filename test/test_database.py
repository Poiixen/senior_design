"""SQLite metadata persistence and repository integration tests."""

import math

import pytest
from sqlalchemy.exc import IntegrityError

from backend.database.connection import (
    create_sqlite_engine,
    initialize_database,
    session_scope,
)
from backend.database.repository import (
    create_analysis,
    create_dataset,
    finish_analysis,
    get_analysis,
    get_dataset,
    get_diagnostic_result,
    list_analyses,
    list_datasets,
    list_diagnostic_results,
    save_diagnostic_result,
)
from backend.models import Analysis, Dataset, DiagnosticResult


@pytest.fixture
def database(tmp_path):
    engine = create_sqlite_engine(tmp_path / "metadata.sqlite3")
    initialize_database(engine)
    yield engine
    engine.dispose()


def add_dataset(session, name="Weather observations"):
    return create_dataset(
        session,
        name=name,
        source="uploaded CSV",
        file_name="weather.csv",
        row_count=12,
        column_count=3,
    )


def test_metadata_round_trip_survives_reopen_and_reinitialization(tmp_path):
    path = tmp_path / "persistent.sqlite3"
    engine = create_sqlite_engine(path)
    initialize_database(engine)
    dataset_name = "Weather'); DROP TABLE datasets; --"
    message = "Sensor's reading contains 'quotes' and a semicolon;"
    with session_scope(engine) as session:
        dataset = add_dataset(session, name=dataset_name)
        analysis = create_analysis(session, dataset.id)
        result = save_diagnostic_result(
            session,
            analysis_id=analysis.id,
            diagnostic_type="missing_values",
            column_name="temperature",
            severity="warning",
            value=0.25,
            message=message,
        )
        dataset_id, analysis_id, result_id = dataset.id, analysis.id, result.id
        assert isinstance(dataset, Dataset)
        assert isinstance(analysis, Analysis)
        assert isinstance(result, DiagnosticResult)
        assert dataset.created_at is not None
    engine.dispose()

    reopened = create_sqlite_engine(path)
    try:
        initialize_database(reopened)
        initialize_database(reopened)
        with session_scope(reopened) as session:
            dataset = get_dataset(session, dataset_id)
            assert dataset.name == dataset_name
            assert dataset.source == "uploaded CSV"
            assert dataset.file_name == "weather.csv"
            assert (dataset.row_count, dataset.column_count) == (12, 3)
            assert get_analysis(session, analysis_id).dataset_id == dataset_id
            result = get_diagnostic_result(session, result_id)
            assert result.analysis_id == analysis_id
            assert result.diagnostic_type == "missing_values"
            assert result.column_name == "temperature"
            assert result.severity == "warning"
            assert result.value == pytest.approx(0.25)
            assert result.message == message
            assert len(list_datasets(session)) == 1
    finally:
        reopened.dispose()


def test_lists_filter_by_parent_and_missing_records_return_none(database):
    with session_scope(database) as session:
        first = add_dataset(session)
        second = add_dataset(session, name="Product catalog")
        first_run = create_analysis(session, first.id)
        second_run = create_analysis(session, first.id)
        other_run = create_analysis(session, second.id)
        first_result = save_diagnostic_result(
            session,
            analysis_id=first_run.id,
            diagnostic_type="duplicate_rows",
            value=2,
        )
        other_result = save_diagnostic_result(
            session,
            analysis_id=other_run.id,
            diagnostic_type="missing_values",
            column_name="sku",
            value=1,
        )
        assert {item.id for item in list_datasets(session)} == {first.id, second.id}
        assert {item.id for item in list_analyses(session, first.id)} == {
            first_run.id,
            second_run.id,
        }
        assert [item.id for item in list_analyses(session, second.id)] == [other_run.id]
        assert [item.id for item in list_diagnostic_results(session, first_run.id)] == [
            first_result.id
        ]
        assert [item.id for item in list_diagnostic_results(session, other_run.id)] == [
            other_result.id
        ]
        assert list_diagnostic_results(session, second_run.id) == []
        assert first_result.column_name is None
        assert first_result.severity == "info"
        assert first_result.message == ""
        assert get_dataset(session, 999999) is None
        assert get_analysis(session, 999999) is None
        assert get_diagnostic_result(session, 999999) is None
        assert list_analyses(session, 999999) == []
        assert list_diagnostic_results(session, 999999) == []


@pytest.mark.parametrize("terminal_status", ["completed", "failed"])
def test_analysis_lifecycle_records_completion(database, terminal_status):
    with session_scope(database) as session:
        dataset = add_dataset(session)
        analysis = create_analysis(session, dataset.id)
        analysis_id = analysis.id
        assert analysis.status == "running"
        assert analysis.started_at is not None
        assert analysis.started_at.tzinfo is None
        assert analysis.completed_at is None
        finish_analysis(session, analysis_id, status=terminal_status)

    with session_scope(database) as session:
        analysis = get_analysis(session, analysis_id)
        assert analysis.status == terminal_status
        assert analysis.completed_at is not None
        assert analysis.completed_at >= analysis.started_at
        assert analysis.completed_at.tzinfo is None


def test_finish_analysis_defaults_to_completed(database):
    with session_scope(database) as session:
        analysis = create_analysis(session, add_dataset(session).id)
        finish_analysis(session, analysis.id)
        assert get_analysis(session, analysis.id).status == "completed"


def test_foreign_keys_reject_orphan_records(database):
    with pytest.raises(IntegrityError):
        with session_scope(database) as session:
            create_analysis(session, 999999)

    with pytest.raises(IntegrityError):
        with session_scope(database) as session:
            save_diagnostic_result(
                session,
                analysis_id=999999,
                diagnostic_type="duplicate_rows",
                value=0,
            )

    with session_scope(database) as session:
        assert list_datasets(session) == []


def test_failed_batch_rolls_back_all_results_without_losing_existing_run(database):
    with session_scope(database) as session:
        analysis_id = create_analysis(session, add_dataset(session).id).id

    with pytest.raises(IntegrityError):
        with session_scope(database) as session:
            save_diagnostic_result(
                session,
                analysis_id=analysis_id,
                diagnostic_type="duplicate_rows",
                value=3,
            )
            save_diagnostic_result(
                session,
                analysis_id=999999,
                diagnostic_type="missing_values",
                value=1,
            )

    with session_scope(database) as session:
        assert get_analysis(session, analysis_id) is not None
        assert list_diagnostic_results(session, analysis_id) == []


def test_session_scope_rolls_back_metadata_after_application_error(database):
    with pytest.raises(RuntimeError, match="cancelled"):
        with session_scope(database) as session:
            add_dataset(session)
            raise RuntimeError("cancelled")

    with session_scope(database) as session:
        assert list_datasets(session) == []


@pytest.mark.parametrize("counts", [(-1, 3), (12, -1)])
def test_negative_dimensions_are_rejected(database, counts):
    with session_scope(database) as session:
        with pytest.raises(ValueError):
            create_dataset(
                session,
                name="Invalid dimensions",
                row_count=counts[0],
                column_count=counts[1],
            )
        assert list_datasets(session) == []


def test_database_constraint_rejects_negative_dimensions(database):
    with pytest.raises(IntegrityError):
        with session_scope(database) as session:
            session.add(Dataset(name="Invalid", row_count=-1, column_count=2))
            session.flush()


@pytest.mark.parametrize("value", [True, "3", math.nan, math.inf, -math.inf])
def test_diagnostic_values_must_be_finite_numeric_scalars(database, value):
    with session_scope(database) as session:
        analysis = create_analysis(session, add_dataset(session).id)
        with pytest.raises(ValueError):
            save_diagnostic_result(
                session,
                analysis_id=analysis.id,
                diagnostic_type="duplicate_rows",
                value=value,
            )
        assert list_diagnostic_results(session, analysis.id) == []


def test_zero_dimensions_and_missing_diagnostic_value_are_supported(database):
    with session_scope(database) as session:
        dataset = create_dataset(session, name="Empty data", row_count=0, column_count=0)
        assert dataset.source is None
        assert dataset.file_name is None
        analysis = create_analysis(session, dataset.id)
        result = save_diagnostic_result(
            session, analysis_id=analysis.id, diagnostic_type="empty_dataset"
        )
        assert result.value is None
        assert result.column_name is None


def test_in_memory_database_is_shared_across_repository_sessions():
    engine = create_sqlite_engine(":memory:")
    try:
        initialize_database(engine)
        with session_scope(engine) as session:
            dataset_id = add_dataset(session).id
        with session_scope(engine) as session:
            assert get_dataset(session, dataset_id).name == "Weather observations"
    finally:
        engine.dispose()
