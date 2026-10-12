
import pandas as pd
import pytest

from backend.diagnostics.validate_column_rules import (
    validate_column_rules,
)
from backend.models.validation_rules import DatasetValidationRules


@pytest.fixture
def rules():
    return DatasetValidationRules(
        version="1.0",
        dataset_name="test",
        columns={
            "age": {
                "type": "integer",
                "required": True,
                "nullable": False,
            },
            "salary": {
                "type": "number",
                "required": True,
                "nullable": True,
            },
            "name": {
                "type": "string",
                "required": True,
                "nullable": False,
            },
            "optional": {
                "type": "string",
                "required": False,
            },
        },
    )


def test_valid_dataset(rules):
    df = pd.DataFrame({
        "age": [20, 30],
        "salary": [100.5, 200],
        "name": ["Alice", "Bob"],
    })

    assert validate_column_rules(df, rules) == []


def test_missing_required_column(rules):
    df = pd.DataFrame({
        "age": [20],
        "salary": [100],
    })

    findings = validate_column_rules(df, rules)

    assert len(findings) == 1
    assert findings[0].diagnostic == "required_column"
    assert findings[0].column == "name"
    assert findings[0].metadata["violation_count"] == 1


def test_invalid_types(rules):
    df = pd.DataFrame({
        "age": [20, "invalid", "42"],
        "salary": [100, "bad", 30.5],
        "name": ["Alice", 123, "Bob"],
    })

    findings = validate_column_rules(df, rules)

    counts = {
        result.column: result.metadata["violation_count"]
        for result in findings
    }

    assert counts == {
        "age": 2,
        "salary": 1,
        "name": 1,
    }


def test_null_not_counted_as_type_error(rules):
    df = pd.DataFrame({
        "age": [20, None],
        "salary": [100, None],
        "name": ["Alice", "Bob"],
    })

    findings = validate_column_rules(df, rules)

    assert len(findings) == 1
    assert findings[0].diagnostic == "nullability"
    assert findings[0].column == "age"
    assert findings[0].metadata["violation_count"] == 1


def test_mixed_type_and_null(rules):
    df = pd.DataFrame({
        "age": [20, "bad", None],
        "salary": [1.5, None, "2.5"],
        "name": ["Alice", "Bob", "Eve"],
    })

    findings = validate_column_rules(df, rules)

    counts = {
        (result.column, result.diagnostic):
        result.metadata["violation_count"]
        for result in findings
    }

    assert counts == {
        ("age", "nullability"): 1,
        ("age", "column_type"): 1,
        ("salary", "column_type"): 1,
    }


def test_numeric_whole_float(rules):
    df = pd.DataFrame({
        "age": [20.0, 30.0],
        "salary": [100, 200.5],
        "name": ["Alice", "Bob"],
    })

    assert validate_column_rules(df, rules) == []


def test_dataset_not_modified(rules):
    df = pd.DataFrame({
        "age": ["42", None],
        "salary": [100, "200"],
        "name": ["Alice", "Bob"],
    })
    original = df.copy(deep=True)

    validate_column_rules(df, rules)

    pd.testing.assert_frame_equal(df, original)


def test_duplicate_column_names_rejected(rules):
    df = pd.DataFrame(
        [[20, 30]],
        columns=["age", "age"],
    )

    with pytest.raises(ValueError, match="unique"):
        validate_column_rules(df, rules)


def test_nullable_missing_markers(rules):
    df = pd.DataFrame({
        "age": pd.Series([20, pd.NA], dtype="Int64"),
        "salary": [100, float("nan")],
        "name": ["Alice", "Bob"],
    })

    findings = validate_column_rules(df, rules)

    assert len(findings) == 1
    assert findings[0].diagnostic == "nullability"
    assert findings[0].metadata["violation_count"] == 1


def test_empty_dataset_required_columns(rules):
    df = pd.DataFrame(columns=["age", "salary", "name"])

    assert validate_column_rules(df, rules) == []
