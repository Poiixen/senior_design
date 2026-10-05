
"""Versioned rules describing expected dataset columns and values."""

import json
import math
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ColumnRule(BaseModel):
    """Expectations for one dataset column."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["integer", "number", "string"]
    required: bool = True
    nullable: bool = True
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: list[Any] | None = None

    @model_validator(mode="after")
    def check_rules(self):
        # Bounds apply only to numeric columns.
        if self.type == "string":
            if self.minimum is not None or self.maximum is not None:
                raise ValueError("String columns cannot have numeric bounds")

        # Reject invalid bounds, including NaN and infinity.
        for bound in (self.minimum, self.maximum):
            if bound is not None:
                if isinstance(bound, bool) or not math.isfinite(bound):
                    raise ValueError("Bounds must be finite numbers")
                if self.type == "integer" and not float(bound).is_integer():
                    raise ValueError("Integer bounds must be whole numbers")

        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("minimum cannot exceed maximum")

        if self.allowed_values is not None:
            if not self.allowed_values:
                raise ValueError("allowed_values cannot be empty")

            for value in self.allowed_values:
                if self.type == "string":
                    valid = isinstance(value, str)
                elif self.type == "integer":
                    valid = type(value) is int
                else:
                    valid = (
                        type(value) in (int, float)
                        and math.isfinite(value)
                    )

                if not valid:
                    raise ValueError(
                        f"Invalid allowed value {value!r} for {self.type}"
                    )

                if self.minimum is not None and value < self.minimum:
                    raise ValueError("Allowed value is below minimum")
                if self.maximum is not None and value > self.maximum:
                    raise ValueError("Allowed value exceeds maximum")

        return self


class DatasetValidationRules(BaseModel):
    """Dataset-specific validation configuration, version 1.0."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal["1.0"]
    dataset_name: str = Field(min_length=1)
    columns: dict[str, ColumnRule] = Field(min_length=1)

    @model_validator(mode="after")
    def check_columns(self):
        if any(not name.strip() for name in self.columns):
            raise ValueError("Column names cannot be blank")
        return self


def load_validation_rules(path: str | Path) -> DatasetValidationRules:
    """Load and validate rules from a JSON file."""
    with open(path, encoding="utf-8") as file:
        data = json.load(file)
    return DatasetValidationRules.model_validate(data)