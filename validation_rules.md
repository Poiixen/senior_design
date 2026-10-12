# Dataset Validation Rules — Version 1.0

## Purpose

The validation-rule configuration defines dataset-specific expectations. It is separate from `DiagnosticResult`, which defines how diagnostic findings are reported.

The same configuration structure is shared by the backend and frontend. The backend validates incoming configurations and uses them when checking datasets.

## Configuration structure

A JSON configuration must contain:

- `version`: Currently `"1.0"`. Unsupported versions are rejected.
- `dataset_name`: Non-empty descriptive dataset identifier.
- `columns`: Non-empty object mapping column names to validation rules.

Each column supports:

| Field | Type | Default | Description |
|---|---|---|---|
| `type` | string | Required | `integer`, `number`, or `string` |
| `required` | boolean | `true` | Column must exist |
| `nullable` | boolean | `true` | Missing cell values are permitted |
| `minimum` | number/null | `null` | Inclusive lower numeric bound |
| `maximum` | number/null | `null` | Inclusive upper numeric bound |
| `allowed_values` | array/null | `null` | Permitted non-missing values |

## Validation semantics

1. `required` applies to **column existence**, not missing cell values.
2. `nullable` applies to missing cells in an existing column.
3. Missing cells are evaluated only against `nullable`, not counted again as type violations.
4. `integer` represents whole-number values, `number` represents finite integers or floating-point values, and `string` represents text.
5. Numeric bounds are inclusive. Both endpoints are valid.
6. String columns cannot define numeric bounds.
7. Integer bounds must be whole numbers.
8. `allowed_values`, if provided, must be a non-empty list containing values consistent with the declared type.
9. Missing values are not listed in `allowed_values`; they are controlled by `nullable`.
10. When a column is absent and `required` is false, its other rules are not evaluated.
11. Unspecified dataset columns are permitted and have no configured expectations.
12. Unknown configuration fields, unsupported types and versions, non-finite bounds, and contradictory bounds are rejected.

## Type-checking policy for future validators

Ticket #32 should inspect dataset values without modifying them.

- Parseable numeric strings, such as `"42"` and `"3.5"`, are treated as strings rather than automatically converted to numbers.
- `integer` requires a numeric whole-number value; `number` accepts numeric integer or floating-point values.
- Boolean values are not treated as numbers.
- Mixed-type columns are checked value by value. Only incompatible non-missing values count as type violations.
- Missing-value detection must recognize standard pandas missing values such as `NaN`, `None`, and `pd.NA`.

## Examples

- `backend/config/adult_rules.json`: Adult Income-shaped dataset.
- `backend/config/sample_rules.json`: Unrelated inventory dataset.

## Backend usage

```python
from backend.models.validation_rules import load_validation_rules

rules = load_validation_rules("backend/config/adult_rules.json")
```

The loaded model can be serialized for the frontend using `rules.model_dump(mode="json")`. Invalid configurations raise Pydantic validation errors.

Configuration loading must not modify the uploaded dataset or produce diagnostic findings. Actual checks and standardized findings belong to the validation implementation in Ticket #32.

## Required-column and type validation (Ticket #32)

The backend uses `validate_column_rules(df, rules)` to check dataset columns without changing uploaded values.

The function returns a list of standardized `DiagnosticResult` findings. An empty list indicates no violations for the checks implemented.

### Type behavior

- `integer`: Numeric whole numbers, including `42.0`, but not `"42"` or booleans.
- `number`: Finite numeric integers or decimals, but not numeric strings like `"3.5"`.
- `string`: Text values only.
- Mixed-type columns: Each non-missing cell is checked individually.
- Missing values: `None`, `NaN`, and `pd.NA` are excluded from type checks. They violate nullability only when `nullable` is false.

### Findings

Three diagnostic identifiers are supported:

- `required_column`: An expected required column does not exist.
- `column_type`: One or more existing values have incompatible types.
- `nullability`: Missing values violate a non-nullable column rule.

Each finding uses `severity="error"` and includes `metadata.violation_count`.

For missing required columns, the violation count is 1 per absent column. For type and nullability findings, it represents the number of affected cells.

The `value` field stores the same count as a floating-point number.

Optional absent columns do not produce findings. Duplicate column names are rejected because they make per-column checks ambiguous.

This validator does not yet evaluate configured numeric bounds or allowed-value restrictions.

can we make a folder for docs also we need to organize the tests.