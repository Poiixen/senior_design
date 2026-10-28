# Column comparisons

Tickets #46 and #51. A user picks two columns from a report's dataset. The
backend compares them, saves the result with the report, and returns it.
Full example responses are in [examples/comparisons/](examples/comparisons/),
generated from the real API.

| `comparison_type` | Columns | Shows | Test |
| --- | --- | --- | --- |
| `categorical_categorical` | `group_column`, `outcome_column` (both categorical) | Contingency table and row percentages | Chi-square test of independence + Cramér's V |
| `categorical_numeric` | `group_column` (categorical), `value_column` (numeric) | Count, mean, median, SD, quartiles per group | Welch's t-test (2 groups) or Kruskal-Wallis (3+ groups) |

Categorical means a text, category, date, or boolean column. Numeric means a
non-boolean number column.

## Endpoints

All endpoints need a logged-in session. A report the user does not own gives
404, the same response as a report that does not exist.

### `POST /api/reports/{analysis_id}/comparisons`

```json
{"comparison_type": "categorical_categorical", "group_column": "education", "outcome_column": "income"}
{"comparison_type": "categorical_numeric", "group_column": "education", "value_column": "age"}
```

| Status | When |
| --- | --- |
| 201 | Saved. The result may still be unavailable; check `status` and `test.status`. |
| 400 | A column does not exist, has the wrong type, or both columns are the same. `detail` explains which. |
| 404 | Report not found or not owned by the user. |
| 409 | The rows for this report were not stored (uploaded before this feature). The user must upload the file again. |
| 422 | Malformed body: unknown `comparison_type`, or a missing or misnamed column field. |

### `GET /api/reports/{analysis_id}/comparisons`

`{"comparisons": [...]}`, oldest first. Each item has the same shape as the
POST response.

### `GET /api/reports/{analysis_id}/comparisons/{comparison_id}`

One saved comparison, unchanged from when it was created.

## Response fields common to both types

| Field | Meaning |
| --- | --- |
| `comparison_id`, `analysis_id`, `created_at` | Saved-record identity. |
| `comparison_type` | Use this to choose the view. |
| `selection` | The columns the user picked. |
| `design` | Always `"independent_groups"`. Paired or repeated measurements are not supported. |
| `status` / `reason` | `"unavailable"` when nothing could be compared: no complete rows, or more than 50 categories. `reason` is user-facing text. |
| `rows` | `total`, `included`, `excluded`, and `exclusion_reasons`. A row missing both values counts under both reasons. |
| `test` | `method` (key, name, what it evaluates, null hypothesis, assumptions), `status`, and `reason`, plus the results when `status` is `"ok"`. |
| `warnings` | Reliability cautions to show beside the result. |
| `note` | Interpretation text to show with the result. |

When a test is unavailable (one category, constant values, too little data),
`test.status` is `"unavailable"` and `test.reason` explains why. Summaries
and tables are still returned.

## `categorical_categorical`

- `group_categories` and `outcome_categories` are labels in descending count
  order (ties sorted by label).
- `counts[i][j]` counts rows in group `i` with outcome `j`.
- `row_percentages[i][j]` is that count as a percentage of `group_totals[i]`
  (`percentage_denominator: "group_total"`).
- `outcome_totals` holds the column totals.
- `test` is Pearson's chi-square test of independence, without continuity
  correction. It returns `statistic`, `degrees_of_freedom`, `p_value`, and
  `expected_counts`.
- `association` is Cramér's V, from 0 to 1.
- Warnings appear when any expected count is below 1, or more than 20% of
  cells are below 5.
- Results are descriptive. Do not present an association as causation or as
  proof of bias; `note` says this.

## `categorical_numeric`

- Rows with a missing group label, or a missing, NaN, or infinite
  measurement, are excluded.
- `overall` and each entry in `groups` have `count`, `mean`, `median`,
  `std_dev`, `min`, `q1`, `q3`, and `max`. Quartiles use linear
  interpolation, as in the column profiles. `std_dev` is null for a group of
  one.
- 2 groups: Welch's t-test (`statistic_name: "t"`, fractional
  `degrees_of_freedom`). `mean_difference` is the first group in
  `difference_order` minus the second. It is unavailable when a group has
  fewer than 2 values or both groups are constant. A warning appears when a
  group has fewer than 30 values.
- 3 or more groups: Kruskal-Wallis (`statistic_name: "H"`,
  `degrees_of_freedom` = groups - 1). It compares ranks, not means; label it
  that way in the UI. It is unavailable when all values are identical or every
  group has one value. A warning appears when a group has fewer than 5 values.
  It does not say which groups differ. Pairwise tests are out of scope.
- `test.group_sizes` lists `{label, count}` per group.

## Category distributions in reports

Each categorical entry in `column_profiles` now has a `distribution` object.
Every existing field is unchanged.

```json
"distribution": {
  "distinct_categories": 3,
  "total_rows": 128, "non_missing_rows": 127, "missing_rows": 1,
  "percentage_denominator": "non_missing_rows",
  "categories": [{"label": "BA", "count": 51, "percentage": 40.16}, ...],
  "categories_truncated": false, "omitted_categories": 0, "omitted_count": 0
}
```

At most 500 categories are listed. When a column has more,
`categories_truncated` is true and the `omitted_*` fields count what was left
out. Reports saved before this change have no `distribution` field.

## Ticket #58: identifier review and regrouping

Both comparison requests accept two optional fields. Requests without them
behave exactly as before.

```json
{
  "comparison_type": "categorical_categorical",
  "group_column": "education",
  "outcome_column": "income",
  "category_mappings": {
    "education": [{"label": "Degree", "categories": ["BA", "MA", "PhD"]}]
  },
  "confirm_columns": ["education"]
}
```

### Identifier review

A categorical column (or an integer column with an identifier-like name) is
flagged for review when at least 90% of its non-missing values are distinct,
or when its name contains `id`, `uuid`, `guid`, `key`, `index`, `idx`,
`serial`, `hash`, `identifier` or `ref` *and* at least 50% of values are
distinct. At least 10 non-missing values are needed. A name alone, or many
repeating categories, never flags a column.

* Column profiles carry `identifier_review` for flagged columns.
* A comparison that groups by a flagged column adds `identifier_review[]`
  (`column`, `role`, `reasons`, `signals`, `confirmed`) and a warning. The
  comparison still runs; nothing is blocked or deleted.
* `confirm_columns` marks flagged columns as meaningful. The warning is then
  omitted and `confirmed` is true; the reasons stay on record. Naming a column
  that is not selected gives 400.

### Category mappings

`category_mappings` maps a selected categorical column to combinations of its
categories. Categories keep their JSON type: `1`, `"1"` and `true` are
different categories. It is applied to a working copy of the selected columns;
the stored rows, the report and earlier comparisons are never changed.
Unmapped categories keep their labels and missing values stay missing.

Rejected with 400 (nothing is saved): a column that is not a selected
categorical column, an empty label, a combination with no categories, a label
used twice, a category that does not exist (the message states its type), a
category listed twice or in two combinations, and a label that collides with an
existing category outside its own combination (a label may equal a member of
its own combination). Malformed bodies give 422. The usual category and table
size limits apply after regrouping.

A regrouped result adds `regrouping`:

| Field | Meaning |
| --- | --- |
| `mappings` | The exact mapping applied, per column. |
| `columns[]` | Per column: `before` and `after` `{label, count}` lists (non-missing rows), `categories_before/after`, `unmapped_categories`, `rows_relabelled`, and missing counts. Feeds before/after charts. |
| `original_comparison_id` | The latest earlier saved comparison of the same columns without a mapping, or null. |
| `method_change` | `group_count_before/after`, `method_before/after`, `changed`, `explanation`. |
| `analysis_id`, `dataset_id` | The report and dataset the mapping belongs to. |
| `note` | A different p-value or fewer warnings do not show the regrouped comparison is more valid. |

Categorical tests also return `test.expected_count_summary` (`cells`,
`cells_below_5`, `cells_below_1`, `share_below_5`, `meets_guideline`).

## Demo pack

[examples/demo-pack/](examples/demo-pack/) has small synthetic datasets, runnable
requests and expected values calculated with scipy and pandas. Rebuild it with
`python scripts/build_demo_pack.py`; `test/test_demo_pack.py` runs it.

[examples/regrouping/](examples/regrouping/) holds real request and response pairs for
identifier warnings, a sparse comparison, a valid combination (with its original
comparison referenced), a combination that still has warnings, a method change and a
rejected mapping. Rebuild them with `python scripts/build_regrouping_examples.py`;
`test/test_regrouping_examples.py` replays each one against the endpoint so they cannot go stale.

## Limits

- Comparisons accept at most 50 categories per column among the included rows
  (`MAX_COMPARISON_CATEGORIES`). Above that, `status` is `"unavailable"` and
  `reason` asks the user to pick another column or combine categories.
- Column profiles list at most 500 categories (`MAX_PROFILE_CATEGORIES`).
