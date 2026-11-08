# Column comparisons

Tickets #46, #51 and #57. A user picks two columns from a report's dataset. The
backend compares them, saves the result with the report, and returns it.
Full example responses are in [examples/comparisons/](examples/comparisons/),
generated from the real API.

| `comparison_type` | Columns | Shows | Test |
| --- | --- | --- | --- |
| `categorical_categorical` | `group_column`, `outcome_column` (both categorical) | Contingency table and row percentages | Chi-square test of independence + Cramér's V |
| `categorical_numeric` | `group_column` (categorical), `value_column` (numeric) | Count, mean, median, SD, quartiles, whiskers per group | `method`: Welch's t-test (2 groups), Welch's ANOVA (3+) or Kruskal-Wallis. Default `auto`: Welch (2) / Kruskal-Wallis (3+) |

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

## Ticket #57: ANOVA, confidence intervals, box plots and distribution shape

Everything below is additive. Requests without `method` behave exactly as
before, and comparisons saved earlier are returned unchanged (they have no
`result_version`; treat a missing value as version 1). Real responses for
every case are in [examples/numeric-pack/responses/](examples/numeric-pack/responses/).

### Choosing a method

```json
{"comparison_type": "categorical_numeric", "group_column": "department", "value_column": "hours", "method": "welch_anova"}
```

| `method` | Question (`analysis_question.key`) | Groups | Notes |
| --- | --- | --- | --- |
| `auto` (default) | depends on the method chosen | any | Welch's t-test for 2 groups, Kruskal-Wallis for 3+ (the Ticket #51 rule). |
| `welch_t_test` | `compare_means` | exactly 2 | Otherwise `test.status` is `"unavailable"` and the reason names the alternatives. |
| `welch_anova` | `compare_means` | 3 or more | With 2 groups it is unavailable and the reason points to `welch_t_test`. |
| `kruskal_wallis` | `compare_ranks` | 2 or more | Rank-based; never present it as a comparison of means. |

An unknown `method` gives 422. Unavailable outcomes still return 201 with
summaries, as before.

### New response fields

| Field | Meaning |
| --- | --- |
| `result_version` | `2` for results saved from Ticket #57 on. |
| `analysis_question` | `{key, text}`. `key` is `compare_means` or `compare_ranks`. |
| `method_selection` | `{requested, selected, rule}`. `rule` explains what `auto` does. |
| `test.method.limitations` | What the method cannot tell you. Show it with the result. Every method says a non-significant p-value is not proof the groups are equal. |
| `overall` / `groups[]`: `whisker_low`, `whisker_high`, `outlier_count` | Tukey box-plot whiskers: the most extreme values within 1.5 × IQR of the quartiles. Values beyond them are counted in `outlier_count`. They use the same quartiles as `q1`/`q3`. |
| `box_plot` | How the quartiles and whiskers were calculated, for chart captions. |

Charts should be drawn from these fields only. The per-group mean chart uses
`groups[].mean`, the summary table uses `groups[]`, and the box plot uses
`min`/`whisker_low`/`q1`/`median`/`q3`/`whisker_high`/`max`. They are the same
numbers the test used.

### Welch's t-test: confidence interval

`test.mean_difference_ci` is returned whenever the test runs:

```json
{"level": 0.95, "lower": -8.91, "upper": -1.09, "standard_error": 1.96,
 "degrees_of_freedom": 72.8, "calculation": "Welch-Satterthwaite interval: ..."}
```

It is the interval for `mean_difference` in the same `difference_order`
(first group minus second): difference ± t(0.975, df) × √(s₁²/n₁ + s₂²/n₂),
with the test's Welch–Satterthwaite df. It matches
`scipy.stats.ttest_ind(..., equal_var=False).confidence_interval(0.95)`. It is
absent when the test is unavailable.

### Welch's one-way ANOVA

This is **Welch's (1951) heteroscedastic ANOVA, not the classical F-test**. It
was chosen to match the Welch t-test, because neither assumes equal variances.
With two groups it is exactly Welch's t-test (F = t²).

* Assumptions: independent rows, and approximately normal group means (roughly
  normal values, or groups large enough). Group variances may differ.
* `statistic_name: "F"`. `degrees_of_freedom` and `degrees_of_freedom_between`
  are k − 1. `degrees_of_freedom_within` is Welch's fractional denominator df.
* `eta_squared` is the between-group sum of squares divided by the total sum of
  squares. It is descriptive and does not adjust for unequal variances.
* It is unavailable when a group has fewer than 2 values or a group has zero
  variance, because each group is weighted by n / s².
* A warning appears when a group has fewer than 30 values.
* The overall test does not identify which groups differ. Post-hoc pairwise
  tests are out of scope.
* It matches `scipy.stats.f_oneway(..., equal_var=False)` (scipy ≥ 1.16).

### Distribution shape in column profiles

Every numeric entry in `column_profiles` gains `distribution_shape`.
`histogram` and the other fields are unchanged.

```json
"distribution_shape": {
  "status": "ok", "reason": null,
  "measure": {"key": "adjusted_fisher_pearson_skewness", "name": "...", "calculation": "...", "thresholds": {}},
  "sample_size": 300, "skewness": 1.63, "standard_error": 0.14,
  "classification": "right_skewed", "strength": "strong",
  "warnings": [], "limitations": ["Approximate symmetry does not mean the values are normally distributed; ..."]
}
```

* Skewness is the adjusted Fisher–Pearson coefficient G1 of the finite values,
  the same as pandas `Series.skew` and `scipy.stats.skew(bias=False)`.
* Thresholds (Bulmer, 1979): |G1| < 0.5 is `approximately_symmetric`. Otherwise
  the column is `left_skewed` (negative) or `right_skewed` (positive), with
  `strength` `moderate` for 0.5 ≤ |G1| < 1 and `strong` for |G1| ≥ 1.
* `standard_error` is √(6n(n−1) / ((n−2)(n+1)(n+3))). With fewer than 50
  values, `warnings` says the classification is tentative.
* `status` is `"unavailable"`, with a `reason`, for fewer than 3 finite values,
  a constant column, or a boolean column.
* Approximate symmetry is never described as normality.

Reports saved before this change have no `distribution_shape`.

## Demo pack

[examples/numeric-pack/](examples/numeric-pack/) is the Ticket #57 pack. It covers:

* Welch's t-test with a known difference
* Welch's ANOVA with unequal groups
* a result without strong evidence of a difference
* missing and non-finite values
* constant and insufficient data
* left-skewed, right-skewed and symmetric distributions

Each case has its question, columns, curl command, expected values from scipy,
expected warnings or unavailable reasons, the visual it supports, and the real
response. Rebuild it with `python scripts/build_numeric_pack.py`.
`test/test_numeric_pack.py` runs it, including save/retrieve and the suggestion
service.

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
