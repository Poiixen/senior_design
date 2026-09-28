"""Service-level transaction and DataFrame integration tests."""

import pandas as pd
import pytest

from backend.database import repository
from backend.database.connection import (
    create_sqlite_engine,
    initialize_database,
    session_scope,
)
from backend.services import AnalysisService
from backend.services import analysis_service as service_module


@pytest.fixture
def engine(tmp_path):
    engine = create_sqlite_engine(tmp_path / "analyses.sqlite3")
    initialize_database(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def service(engine):
    return AnalysisService(engine)


def test_register_and_analyze_generic_dataframe(service, engine):
    df = pd.DataFrame({17: [1, 1, None], "reading": ["ok", "ok", "bad"]})
    original = df.copy(deep=True)

    dataset = service.register_dataset(
        df, name="Sensor readings", source="upload", file_name="sensors.csv"
    )
    analysis = service.run_analysis(dataset.id, df)

    assert dataset.name == "Sensor readings"
    assert dataset.source == "upload"
    assert dataset.file_name == "sensors.csv"
    assert (dataset.row_count, dataset.column_count) == (3, 2)
    assert analysis.dataset_id == dataset.id
    assert analysis.status == "completed"
    assert analysis.started_at is not None
    assert analysis.completed_at >= analysis.started_at
    pd.testing.assert_frame_equal(df, original)

    with session_scope(engine) as session:
        results = repository.list_diagnostic_results(session, analysis.id)
    assert len(results) == 2
    by_type = {result.diagnostic_type: result for result in results}
    missing = by_type["missing_values"]
    assert missing.column_name == "17"
    assert missing.severity == "high"
    assert missing.value == pytest.approx(100 / 3)
    assert "1 of 3" in missing.message
    assert "33.33%" in missing.message
    duplicates = by_type["duplicates"]
    assert duplicates.column_name is None
    assert duplicates.severity == "warning"
    assert duplicates.value == pytest.approx(100 / 3)
    assert "1 of 3" in duplicates.message
    assert "33.33%" in duplicates.message


@pytest.mark.parametrize(
    "df",
    [
        pd.DataFrame({"label": ["a", "b"], "measurement": [2, 3]}),
        pd.DataFrame(columns=["label", "measurement"]),
    ],
    ids=["clean", "empty"],
)
def test_clean_and_empty_dataframes_keep_zero_duplicate_summary(service, engine, df):
    original = df.copy(deep=True)
    dataset = service.register_dataset(df, name="Readings")
    analysis = service.run_analysis(dataset.id, df)

    with session_scope(engine) as session:
        results = repository.list_diagnostic_results(session, analysis.id)

    assert analysis.status == "completed"
    assert len(results) == 1
    assert results[0].diagnostic_type == "duplicates"
    assert results[0].severity == "none"
    assert results[0].value == 0.0
    assert f"0 of {len(df)}" in results[0].message
    pd.testing.assert_frame_equal(df, original)


def test_running_analysis_is_committed_before_diagnostics(service, engine, monkeypatch):
    df = pd.DataFrame({"label": ["a"]})
    dataset = service.register_dataset(df, name="Readings")
    original_detector = service_module.detect_missing_values

    def inspect_running_run(frame):
        with session_scope(engine) as session:
            analyses = repository.list_analyses(session, dataset.id)
            assert len(analyses) == 1
            assert analyses[0].status == "running"
            assert analyses[0].completed_at is None
            assert repository.list_diagnostic_results(session, analyses[0].id) == []
        return original_detector(frame)

    monkeypatch.setattr(service_module, "detect_missing_values", inspect_running_run)
    assert service.run_analysis(dataset.id, df).status == "completed"


def test_detector_failure_records_failed_run(service, engine, monkeypatch):
    df = pd.DataFrame({"label": ["a"]})
    dataset = service.register_dataset(df, name="Readings")

    def fail_detector(frame):
        raise RuntimeError("Detector failed")

    monkeypatch.setattr(service_module, "detect_duplicates", fail_detector)
    with pytest.raises(RuntimeError, match="Detector failed"):
        service.run_analysis(dataset.id, df)

    with session_scope(engine) as session:
        analyses = repository.list_analyses(session, dataset.id)
        assert len(analyses) == 1
        assert analyses[0].status == "failed"
        assert analyses[0].completed_at >= analyses[0].started_at
        assert repository.list_diagnostic_results(session, analyses[0].id) == []


def test_insert_failure_rolls_back_all_findings(service, engine, monkeypatch):
    df = pd.DataFrame({"label": ["a", None]})
    dataset = service.register_dataset(df, name="Readings")
    original_save = repository.save_diagnostic_result
    insert_count = 0

    def fail_second_insert(*args, **kwargs):
        nonlocal insert_count
        insert_count += 1
        if insert_count == 2:
            raise RuntimeError("Second insert failed")
        result = original_save(*args, **kwargs)
        args[0].flush()
        return result

    monkeypatch.setattr(repository, "save_diagnostic_result", fail_second_insert)
    with pytest.raises(RuntimeError, match="Second insert failed"):
        service.run_analysis(dataset.id, df)

    assert insert_count == 2
    with session_scope(engine) as session:
        analyses = repository.list_analyses(session, dataset.id)
        assert len(analyses) == 1
        assert analyses[0].status == "failed"
        assert analyses[0].completed_at is not None
        assert repository.list_diagnostic_results(session, analyses[0].id) == []


def test_repeat_runs_remain_separate(service, engine):
    df = pd.DataFrame({"label": ["a", "a"]})
    dataset = service.register_dataset(df, name="Readings")
    first = service.run_analysis(dataset.id, df)
    second = service.run_analysis(dataset.id, df)

    assert first.id != second.id
    with session_scope(engine) as session:
        analyses = repository.list_analyses(session, dataset.id)
        assert {analysis.id for analysis in analyses} == {first.id, second.id}
        for analysis in analyses:
            assert analysis.status == "completed"
            results = repository.list_diagnostic_results(session, analysis.id)
            assert len(results) == 1
            assert results[0].analysis_id == analysis.id
            assert results[0].value == 50.0


def test_missing_dataset_is_rejected_without_creating_run(service, engine):
    with pytest.raises(ValueError, match="Dataset 999 does not exist"):
        service.run_analysis(999, pd.DataFrame({"label": ["a"]}))

    with session_scope(engine) as session:
        assert repository.list_analyses(session, 999) == []
