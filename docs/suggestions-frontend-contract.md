# Suggestions frontend contract

The report interface expects the Ticket #47 backend at:

`POST /api/reports/{analysis_id}/suggestions`

The operation must require the existing authenticated session and return 404
when the report is missing or belongs to another user. The response shape is:

```json
{
  "analysis_id": 42,
  "source": "ai",
  "suggestions": [
    {
      "title": "Review missing age values",
      "affected_columns": ["age"],
      "explanation": "Age is missing in a material share of rows.",
      "evidence": ["18 of 120 rows are missing age (15.00%)."],
      "next_steps": ["Confirm why age is missing before choosing an imputation method."]
    }
  ]
}
```

`source` must be either `ai` or `fallback`. Every list must be present even
when empty. The frontend prevents duplicate submissions, supports retry and
empty results, aborts an in-flight request when the report changes, and
rejects a response whose `analysis_id` does not match the current report.

## Extended response (additive)

Everything above is unchanged. The fields below are additive, so a client that
only reads the original fields keeps working. Models live in
`backend/models/suggestions.py`; runnable samples are in
`docs/examples/suggestions/`.

### Request (optional body)

The frontend may keep sending no body. When it does send one:

| Field | Default | Meaning |
| --- | --- | --- |
| `comparison_ids` | all saved comparisons of the report | Comparisons to include. An id that does not belong to this report gives 400 (404 if the report is not the user's). |
| `limit` | 5 (max 20) | Findings returned. |
| `offset` | 0 | Skip this many ranked findings, to read the rest. |

### Top-level fields

| Field | Meaning |
| --- | --- |
| `comparison_ids_used` | Comparison ids the findings were built from. |
| `evidence_fingerprint` | Hash of the report id and of the used comparisons' ids and `created_at`. |
| `total_findings` | Findings found across all pages. |
| `offset`, `has_more` | Paging state. |
| `unavailable_analyses` | Analyses with no saved result (for example `anova`, `regrouping`). Nothing is implied about them. |

### Outdated output

Keep `evidence_fingerprint` and `comparison_ids_used` with the displayed
result. Treat it as outdated when the report's saved comparison list no longer
matches `comparison_ids_used` (when no `comparison_ids` were requested), or
when a request for the same ids returns a different fingerprint. Show a notice
and offer "Regenerate suggestions".

### Per-suggestion fields

| Field | Meaning |
| --- | --- |
| `finding_id` | Stable for the same evidence, for example `missing_values-age`. |
| `finding_type` | `missing_values`, `duplicates`, `outliers`, `correlation`, `group_difference`, `categorical_association`, `skewed_distribution`, `unavailable_test`, `small_groups`, `regrouping`. |
| `priority`, `priority_percent` | `high`/`medium`/`low` and a 0-100 ranking score. It orders findings; it is not a probability. |
| `priority_reason` | Plain-language reason for the priority. |
| `evidence_refs` | Saved results the finding came from (`result_type`, `analysis_id`, `comparison_id`, `column`). |
| `evidence_values` | Backend numbers behind the text: statistic, degrees of freedom, p-value, effect size and measure, group sizes, means and medians. With several tested comparisons it also has `p_value_adjusted` and `p_adjustment` (Holm). |
| `warnings` | Reliability warnings. Show them before the explanation. |
| `exploratory` | True when several user-selected comparisons were examined. Never present as a confirmed discovery. |
| `visual` | Chart specification, below. |

### `visual`

`chart_type` is one of `bar`, `histogram`, `box_plot`, `grouped_box`,
`grouped_percentage_bar`, `contingency_heatmap`, `correlation_pair`,
`before_after_bar`, `evidence_table`. `data` holds saved aggregates only.
`source`, `x_label`, `y_label`, `units`, `percent_denominator`, `warnings` and
`unavailable_fields` describe it. When the evidence cannot support a chart the
type is `evidence_table`, `fallback_reason` says why, and
`data.rows` is `[{"label", "value"}]`. The frontend must render an unknown
`chart_type` as a table of `data` rather than failing.

### Source

`source` is `ai` only when optional wording was applied and validated;
otherwise `fallback`. In both cases ranking, evidence and chart values are the
same.
