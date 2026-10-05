"""Service-level transaction and DataFrame integration tests."""

import json

import pandas as pd
import pytest

from backend.database import repository
from backend.database.connection import (
    create_sqlite_engine,
    initialize_database,
    session_scope,
)
from backend.models.schemas import AnalysisReport, DiagnosticResult
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


def _by_type(results):
    grouped = {}
    for result in results:
        grouped.setdefault(result.diagnostic_type, []).append(result)
    return grouped


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

    results = service.list_findings(analysis.id)
    assert len(results) == 6
    by_type = _by_type(results)

    (validation,) = by_type["validation"]
    assert validation.severity == "warning"
    assert validation.column_name is None
    assert "extremely small" in validation.message

    profile = {result.column_name: result for result in by_type["profile"]}
    assert set(profile) == {"17", "reading"}
    assert profile["17"].severity == "info"
    assert profile["17"].value == 1.0
    assert "Numeric column (float64)" in profile["17"].message
    assert profile["reading"].value == 2.0
    assert "Categorical column" in profile["reading"].message

    (missing,) = by_type["missing_values"]
    assert missing.column_name == "17"
    assert missing.severity == "high"
    assert missing.value == pytest.approx(100 / 3)
    assert "1 of 3" in missing.message
    assert "33.33%" in missing.message

    (duplicates,) = by_type["duplicates"]
    assert duplicates.column_name is None
    assert duplicates.severity == "warning"
    assert duplicates.value == pytest.approx(100 / 3)
    assert "1 of 3" in duplicates.message
    assert "33.33%" in duplicates.message

    (outliers,) = by_type["outliers"]
    assert outliers.column_name == "17"
    assert outliers.severity == "none"
    assert outliers.value == 0.0


def test_clean_dataframe_keeps_zero_summaries(service, simple_clean_df):
    original = simple_clean_df.copy(deep=True)
    dataset = service.register_dataset(simple_clean_df, name="Readings")
    analysis = service.run_analysis(dataset.id, simple_clean_df)

    by_type = _by_type(service.list_findings(analysis.id))

    assert analysis.status == "completed"
    assert set(by_type) == {"profile", "duplicates", "outliers"}
    assert len(by_type["profile"]) == 3
    (duplicates,) = by_type["duplicates"]
    assert duplicates.severity == "none"
    assert duplicates.value == 0.0
    assert "0 of 6" in duplicates.message
    assert {result.column_name for result in by_type["outliers"]} == {"id", "score"}
    assert all(result.severity == "none" for result in by_type["outliers"])
    pd.testing.assert_frame_equal(simple_clean_df, original)


def test_outliers_are_recorded_per_numeric_column(service, numeric_outliers_df):
    dataset = service.register_dataset(numeric_outliers_df, name="Readings")
    analysis = service.run_analysis(dataset.id, numeric_outliers_df)

    outliers = {
        result.column_name: result
        for result in _by_type(service.list_findings(analysis.id))["outliers"]
    }

    assert set(outliers) == {"value", "clean"}
    assert outliers["value"].severity == "warning"
    assert outliers["value"].value == pytest.approx(2 / 11 * 100)
    assert "2 values" in outliers["value"].message
    assert "[-5, 15]" in outliers["value"].message
    assert outliers["clean"].severity == "none"


DOWNSTREAM_DIAGNOSTICS = (
    "profile_dataset",
    "detect_numeric_outliers",
)


@pytest.mark.parametrize(
    "df, expected_error",
    [
        (pd.DataFrame(columns=["label", "measurement"]), "Dataset is empty"),
        (
            pd.DataFrame([[1, 2], [3, 4]], columns=["a", "a"]),
            "Duplicate column names",
        ),
    ],
    ids=["empty", "duplicate-columns"],
)
def test_structural_errors_block_downstream_diagnostics(
    service, monkeypatch, df, expected_error
):
    def must_not_run(frame):
        raise AssertionError("Downstream diagnostic ran on an invalid dataset")

    for name in DOWNSTREAM_DIAGNOSTICS:
        monkeypatch.setattr(service_module, name, must_not_run)

    dataset = service.register_dataset(df, name="Readings")
    analysis = service.run_analysis(dataset.id, df)
    results = service.list_findings(analysis.id)

    assert analysis.status == "completed"
    assert {result.diagnostic_type for result in results} == {"validation"}
    errors = [result for result in results if result.severity == "error"]
    assert any(expected_error in result.message for result in errors)


def test_validation_runs_before_other_diagnostics(service, monkeypatch):
    df = pd.DataFrame({"label": ["a"], "measurement": [1]})
    dataset = service.register_dataset(df, name="Readings")
    calls = []

    for name in ("validate_dataset",) + DOWNSTREAM_DIAGNOSTICS:
        original = getattr(service_module, name)

        def record(frame, _name=name, _original=original):
            calls.append(_name)
            return _original(frame)

        monkeypatch.setattr(service_module, name, record)

    service.run_analysis(dataset.id, df)

    assert calls[0] == "validate_dataset"
    assert set(calls[1:]) == set(DOWNSTREAM_DIAGNOSTICS)


def test_running_analysis_is_committed_before_diagnostics(service, engine, monkeypatch):
    df = pd.DataFrame({"label": ["a"]})
    dataset = service.register_dataset(df, name="Readings")
    original_detector = service_module.profile_dataset

    def inspect_running_run(frame):
        with session_scope(engine) as session:
            analyses = repository.list_analyses(session, dataset.id)
            assert len(analyses) == 1
            assert analyses[0].status == "running"
            assert analyses[0].completed_at is None
            assert repository.list_diagnostic_results(session, analyses[0].id) == []
        return original_detector(frame)

    monkeypatch.setattr(service_module, "profile_dataset", inspect_running_run)
    assert service.run_analysis(dataset.id, df).status == "completed"


def test_missing_and_duplicate_detection_run_once(service, monkeypatch):
    from backend.diagnostics import generic_dataset_profiler as profiler

    df = pd.DataFrame({"label": ["a", "a", None], "measurement": [1, 1, 2]})
    dataset = service.register_dataset(df, name="Readings")
    calls = []

    for name in ("detect_missing_values", "detect_duplicates"):
        original = getattr(profiler, name)

        def record(frame, _name=name, _original=original):
            calls.append(_name)
            return _original(frame)

        monkeypatch.setattr(profiler, name, record)

    service.run_analysis(dataset.id, df)

    assert sorted(calls) == ["detect_duplicates", "detect_missing_values"]


def test_report_is_saved_with_findings(service):
    df = pd.DataFrame({"label": ["a", "a", None], "measurement": [1, 1, 2]})
    dataset = service.register_dataset(df, name="Readings")
    analysis = service.run_analysis(dataset.id, df)

    report = service.get_report(analysis.id)
    findings = service.list_findings(analysis.id)

    assert report.dataset_id == dataset.id
    assert report.analysis_id == analysis.id
    assert (report.profile.rows, report.profile.columns, report.valid) == (3, 2, True)
    assert report.status == "completed"
    assert report.completed_at == analysis.completed_at
    assert len(report.findings) == len(findings)
    assert [f.diagnostic for f in report.findings] == [
        f.diagnostic_type for f in findings
    ]
    assert report.summary.issues_detected == sum(
        f.severity not in {"none", "info"} for f in findings
    )


def test_invalid_dataset_report_is_not_valid(service):
    df = pd.DataFrame(columns=["label", "measurement"])
    dataset = service.register_dataset(df, name="Readings")
    analysis = service.run_analysis(dataset.id, df)

    report = service.get_report(analysis.id)

    assert report.valid is False
    assert report.profile.column_details == []
    assert {f.diagnostic for f in report.findings} == {"validation"}


def test_failed_run_saves_no_report(service, monkeypatch):
    df = pd.DataFrame({"label": ["a"]})
    dataset = service.register_dataset(df, name="Readings")

    def fail(frame):
        raise RuntimeError("Detector failed")

    monkeypatch.setattr(service_module, "profile_dataset", fail)
    with pytest.raises(RuntimeError):
        service.run_analysis(dataset.id, df)

    assert service.get_report(1) is None


@pytest.mark.parametrize("detector", ("validate_dataset",) + DOWNSTREAM_DIAGNOSTICS)
def test_detector_failure_records_failed_run(service, engine, monkeypatch, detector):
    df = pd.DataFrame({"label": ["a"], "measurement": [1]})
    dataset = service.register_dataset(df, name="Readings")

    def fail_detector(frame):
        raise RuntimeError("Detector failed")

    monkeypatch.setattr(service_module, detector, fail_detector)
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
            assert all(result.analysis_id == analysis.id for result in results)
            (duplicates,) = _by_type(results)["duplicates"]
            assert duplicates.value == 50.0


def test_missing_dataset_is_rejected_without_creating_run(service, engine):
    with pytest.raises(ValueError, match="Dataset 999 does not exist"):
        service.run_analysis(999, pd.DataFrame({"label": ["a"]}))

    with session_scope(engine) as session:
        assert repository.list_analyses(session, 999) == []


def test_report_round_trips_without_losing_fields(service):
    df = pd.DataFrame({"label": ["a", "a", None], "measurement": [1, 1, 2]})
    dataset = service.register_dataset(df, name="Readings")
    analysis = service.run_analysis(
        dataset.id, df, parsing_options={"sep": ",", "encoding": "utf-8"}
    )

    saved = service.get_report(analysis.id)
    original = AnalysisReport.model_validate_json(saved.to_json())

    assert saved == original
    assert saved.schema_version == 1
    assert saved.parsing_options == {"sep": ",", "encoding": "utf-8"}
    assert saved.profile.numeric_columns == ["measurement"]
    assert saved.profile.categorical_columns == ["label"]
    by_diag = {f.diagnostic: f for f in saved.findings if f.is_issue}
    assert by_diag["missing_values"].metadata == {"missing_count": 1, "total_rows": 3}
    assert by_diag["missing_values"].recommendation
    assert by_diag["duplicates"].metadata["duplicate_count"] == 1
    assert saved.summary.issues_by_diagnostic["duplicates"] == 1


def test_non_finite_numbers_become_null_and_json_is_valid():
    finding = DiagnosticResult(
        diagnostic="outliers",
        severity="warning",
        value=float("nan"),
        message="x",
        metadata={"lower_bound": float("-inf"), "nested": [float("inf"), 1.5]},
    )

    assert finding.value is None
    assert finding.metadata == {"lower_bound": None, "nested": [None, 1.5]}
    json.loads(finding.model_dump_json(), parse_constant=_reject_constant)


def _reject_constant(name):
    raise AssertionError(f"Non-standard JSON constant: {name}")


def test_initialize_database_adds_report_table_and_keeps_records(tmp_path):
    from sqlalchemy import inspect, text

    engine = create_sqlite_engine(tmp_path / "old.sqlite3")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE datasets (id INTEGER PRIMARY KEY, name TEXT, source TEXT, "
            "file_name TEXT, row_count INTEGER, column_count INTEGER, created_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO datasets (name, row_count, column_count) VALUES ('old', 1, 1)"
        ))

    initialize_database(engine)

    assert "analysis_reports" in inspect(engine).get_table_names()
    with session_scope(engine) as session:
        assert [d.name for d in repository.list_datasets(session)] == ["old"]
    engine.dispose()
