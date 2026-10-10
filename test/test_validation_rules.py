
import pytest
from pydantic import ValidationError

from backend.models.validation_rules import (
    ColumnRule,
    DatasetValidationRules,
    load_validation_rules,
)


def test_valid_configuration():
    rules = DatasetValidationRules(
        version="1.0",
        dataset_name="test",
        columns={
            "age": ColumnRule(
                type="integer",
                required=True,
                nullable=False,
                minimum=0,
                maximum=120,
            )
        },
    )

    assert rules.columns["age"].minimum == 0


@pytest.mark.parametrize("invalid", [
    {"type": "boolean"},
    {"type": "date"},
    {"type": "integer", "minimum": 100, "maximum": 10},
    {"type": "string", "minimum": 0},
    {"type": "integer", "minimum": 1.5},
    {"type": "integer", "allowed_values": ["hello"]},
    {"type": "number", "allowed_values": [True]},
    {"type": "string", "allowed_values": []},
    {"type": "number", "minimum": float("nan")},
    {"type": "integer", "unknown_rule": True},
])
def test_invalid_column_rules(invalid):
    with pytest.raises(ValidationError):
        ColumnRule(**invalid)


def test_unknown_version_rejected():
    with pytest.raises(ValidationError):
        DatasetValidationRules(
            version="2.0",
            dataset_name="test",
            columns={"age": {"type": "integer"}},
        )


def test_unknown_configuration_key_rejected():
    with pytest.raises(ValidationError):
        DatasetValidationRules(
            version="1.0",
            dataset_name="test",
            columns={"age": {"type": "integer"}},
            unexpected=True,
        )


@pytest.mark.parametrize("filename", [
    "adult_rules.json",
    "sample_rules.json",
])
def test_example_configs_load(filename):
    rules = load_validation_rules(
        f"backend/config/{filename}"
    )
    assert rules.version == "1.0"
    assert rules.columns
