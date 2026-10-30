# How suggestions are selected and ranked

`POST /api/reports/{analysis_id}/suggestions` reads only the report's saved
results. Selection, ranking, evidence values and chart values are computed by
the backend; the optional AI step may only reword text.

## 1. Evidence

* The report must belong to the signed-in user (404 otherwise).
* Missing values, duplicates, outliers, correlation and column profiles come
  from the saved report. Any section may be absent in older reports.
* Comparisons come from the report's saved comparisons. With no
  `comparison_ids` all of them are used. An id from another report, or another
  user's report, gives 400.
* `unavailable_analyses` lists analyses with no saved result (`anova`,
  `distribution`, `regrouping`). Text never mentions an analysis that has no
  result.
* `evidence_fingerprint` hashes the report id and the used comparisons' ids and
  `created_at`.

## 2. Selection thresholds

A rule produces a finding only when its pattern passes the threshold, so a
clean report returns an empty list.

| Finding | Surfaced when |
| --- | --- |
| `missing_values` | column missing percentage >= 5% |
| `duplicates` | duplicate row count > 0 (existing duplicate definition) |
| `outliers` | column outlier percentage >= 1% |
| `correlation` | \|Pearson r\| >= 0.7 for a column pair |
| `skewed_distribution` | \|skewness\| >= 1 (needs the Ticket #57 distribution result) |
| `group_difference` | a selected numeric comparison whose test ran |
| `categorical_association` | a selected categorical comparison whose test ran |
| `unavailable_test` / `small_groups` | a selected comparison whose test could not run |
| `regrouping` | a selected comparison that carries a user regrouping (Ticket #58) |

## 3. Score

```
score = reliability * (0.6 * size + 0.4 * coverage)
```

All three terms are 0-1. `priority_percent = round(100 * score)`; it orders
findings and is not a probability. Bands: high >= 0.75, medium >= 0.45, else low.

| Term | Meaning |
| --- | --- |
| size | how large the pattern is: missing % / 30, duplicate % / 20, outlier % / 10 (each capped at 1); correlation `(\|r\| - 0.5) / 0.5`; skewness / 3; comparisons use an observed effect (two-group standardised mean difference, or range of group means/medians over the overall standard deviation; Cramer's V / 0.5), capped at 1 |
| coverage | share of observations involved: the affected rows, the rows used by a comparison, or non-missing rows for a whole-column property |
| reliability | 1 for >= 30 supporting rows, 0.7 for 5-29, 0.4 for fewer; multiplied by 0.75 when the comparison carries its own reliability warnings; 0.4 when the test could not run |

p-values never enter the score. A non-significant comparison (p >= 0.05) has its
size halved and is described as "did not detect a difference". When two or more
tested comparisons are selected they are all marked `exploratory` with a
multiple-comparison warning, and the smallest p-value is never presented as a
discovery. Their p-values are adjusted with Holm's method (re-running the same
selection counts once, using the latest result); `evidence_values` then holds
`p_value_adjusted` and `p_adjustment` (`method`, `comparisons`), and
`significant_at_0_05` is read from the adjusted value. A result significant only
before adjustment has its size halved like any non-significant result.

## 4. Deduplication, order and paging

* The same `finding_id` is kept once.
* Outliers and skew on one column keep the higher score; the other's reference
  is added to `evidence_refs` and listed in `evidence_values.also_covers`.
* Repeats of one comparison selection keep the most recent comparison.
* Order is score descending, ties broken by `finding_id`, so the same evidence
  always gives the same list.
* `limit` (default 5, max 20) and `offset` page through `total_findings`.

## 5. Wording

Deterministic text (`fallback.py`) is always produced first. It puts warnings
before interpretation, names the method that ran, keeps mean comparisons apart
from rank comparisons, never reads non-significance as equality, never names
differing groups from a multi-group test alone, recommends review rather than
deletion, and makes no causal, fairness or demographic claims.

With `ANTHROPIC_API_KEY` set and the `anthropic` package installed, compact
aggregates (no rows or cell values) are sent and the model may replace each
finding's title, explanation and next steps. Replies are discarded, and the
deterministic text kept (`source: "fallback"`), if they are not valid JSON,
do not cover exactly the findings sent, exceed length limits, contain a number
not present in the finding's evidence, or contain banned wording. Warnings are
re-attached by the backend. The model name defaults to `claude-haiku-5-5` and
can be set with `SUGGESTIONS_AI_MODEL`.

## 6. Dependencies on other tickets

* #58 (regrouping, identifier review): verified against its real output in
  `test/test_api_suggestions.py`. Regrouping is read from a comparison's
  `regrouping.columns[]` (`before`/`after` counts, `mapping`) and
  `regrouping.method_change`, with one finding per regrouped column. A changed
  method is shown as a warning, and the text states that a different p-value or
  fewer warnings do not show the regrouped comparison is more valid.
  Identifier-review warnings arrive through the comparison's own `warnings`.
* #57 (ANOVA, distribution shape): **not yet verified against real results.**
  ANOVA is recognised by a method key containing `anova` and treated as a mean
  comparison, with `eta_squared` and a Welch `mean_difference_ci` shown when
  present. Skewness is read from `distribution_shape.skewness` on numeric column
  profiles, and group box plots use `whisker_low`/`whisker_high` when present.
  These shapes are assumptions until the #57 results exist; adjust `rules.py`
  if they differ. Reports without them simply produce no such findings.
