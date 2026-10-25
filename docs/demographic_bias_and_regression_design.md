# Demographic-Outcome Measure and Regression Workflow: Design Proposal

Ticket #52 · Research prototype, not a production feature

This document proposes one demographic measure and one regression workflow.
It is written so the methods can be reviewed without reading the code. Every
number quoted below comes from the reproducible prototype in
[research/demographic_regression_prototype.py](../research/demographic_regression_prototype.py),
run on synthetic data (section 3).

**Status:** proposal for advisor review. Nothing here is exposed in the API,
stored in the database, or shown on the dashboard.

**Builds on Ticket #46** (categorical comparisons, PR #94). The group-rate
table is computed from the #46 contingency table, and the predictor review
uses the #46 chi-square / Cramér's V and numeric-across-groups comparisons.
See [comparisons.md](comparisons.md) for those methods. The prototype assumes
PR #94 has been merged to `main`.

---

## Summary

| | Proposal |
| --- | --- |
| Replaces "demographic bias" with | *Does the observed rate of a binary outcome differ between groups of one demographic column, compared with a chosen reference group?* |
| Descriptive measure | Per-group outcome rate with a 95% Wilson interval, plus the difference (percentage points) and ratio against the reference group. Derived from the Ticket #46 contingency table and shown alongside its chi-square test and Cramér's V |
| Relationship to #46 | #46 answers "are these two columns associated?" for any pair of columns. This adds the reference-group view a demographic question needs: which group, in which direction, by how much, and how certain |
| Regression | Logistic regression for a binary outcome, unpenalized, one-hot encoding with explicit reference levels |
| Evaluation | Stratified 75/25 train/test split; all preprocessing fit on training rows only; ROC AUC, Brier score, accuracy against a majority-class baseline, calibration-in-the-large |
| What it will not say | Whether a dataset, process or model is fair or unfair, or why a gap exists |

---

## 1. Demographic analysis question

### 1.1 The question

We considered two starting points:

- **Representation:** is each group present in the data in the proportion
  we would expect?
- **Outcome rates:** among the rows in the data, does the rate of a given
  outcome differ between groups?

**We propose starting with outcome-rate differences.** It can be answered
from the dataset alone, so it fits a tool that accepts arbitrary uploads.
Representation needs an external population benchmark (for example, census
shares for the population the data claims to cover), and the right benchmark
depends on how the data was collected. Section 1.6 explains how the
representation question can be added later. The group shares are still
reported alongside the rates as context.

> **Question:** For a binary outcome column *Y* and a group column *G*, what is
> the observed rate of *Y = positive value* within each level of *G*, and how
> does each group's rate compare with that of a stated reference group?

### 1.2 Required inputs

| Input | Required | Description | Prototype value |
| --- | --- | --- | --- |
| Group column | Yes | One nominal column holding group membership | `group` (Group A–D) |
| Outcome column | Yes | One column with two outcome values | `high_income` (0/1) |
| Positive value | Yes | Which outcome value counts as "the outcome" | `1` |
| Reference group | Yes | The group every other group is compared to. Must be chosen by the user and documented; it is a reporting convention, not a claim that this group is "normal" | `Group A` (the largest group) |
| Minimum group size | No, default 30 | Groups smaller than this are flagged as unstable | 30 |
| Population benchmark | **Not used** for this question | Only needed for the representation question (section 1.6) | — |

The tool should never guess the group column, outcome column or reference
group. A user (or analyst) must name them.

### 1.3 The measure

For each group *g*, using only rows where the outcome is recorded:

| Quantity | Definition |
| --- | --- |
| *n* | Number of rows in the group |
| Share | *n* as a percentage of all rows with an outcome |
| Rate | Positive outcomes ÷ *n*, as a percentage |
| 95% interval | Wilson score interval for the rate. Chosen over the simple ± 1.96·SE interval because it behaves sensibly for small groups and for rates near 0% or 100% |
| Difference | Group rate − reference rate, in **percentage points** |
| Ratio | Group rate ÷ reference rate. Reported as unavailable if the reference rate is 0 |

Both the difference and the ratio are reported because they can tell
different stories: a gap from 2% to 4% is only 2 points but a ratio of 2.0,
while a gap from 50% to 60% is 10 points but a ratio of 1.2.

**How it relates to the Ticket #46 comparison.** For the same two columns,
#46 already returns the group × outcome contingency table, its row
percentages (which are these rates), a chi-square test of independence and
Cramér's V. The measure is computed directly from that table, so the two can
never disagree. It adds only what #46 deliberately leaves out:

| #46 categorical comparison | Added here |
| --- | --- |
| Is there *any* association across all groups? (chi-square, one p-value) | Which groups differ from the chosen reference, and in which direction |
| How strong overall? (Cramér's V, 0–1, no direction) | Gap in percentage points and as a ratio, per group |
| Row percentages, no uncertainty | 95% interval on each group's rate |
| Rows missing the group are excluded | Rows missing the group are kept as their own row |
| Expected-count warnings for the chi-square test | Small-group flag on individual rates |

Both are reported together. The chi-square result is computed on rows with a
recorded group, exactly as the #46 API would report it.

Two practical points carried over from #46: an outcome stored as numbers
(0/1) is treated as two categories, and columns with more than 50 categories
are refused.

### 1.4 Missing values and small groups

- **Missing outcome:** the row is excluded from every rate, and the number
  of excluded rows is reported. If outcomes are missing more often in some
  groups, that is itself worth knowing (see advisor question 3).
- **Missing group:** the row is **kept**, as its own "(missing)" row in the
  table. Dropping it would hide the fact that demographics were not
  recorded, and the outcome rate among unrecorded rows can differ from the rest.
- **Small groups** (fewer than 30 rows by default): the numbers are still
  shown, never hidden, but flagged "small group: unstable." The wide
  Wilson interval shows the same thing in numbers. We do **not** merge small
  groups into an "Other" category automatically, because which groups can
  meaningfully be combined is a substantive decision, not a statistical one.
- **Privacy:** for real data about people, very small cells (e.g. fewer than 5 to 10)
  may need to be suppressed rather than shown. This is not implemented; see
  advisor question 4.

### 1.5 Why a difference does not establish unfairness

An observed gap in outcome rates is a description of the data, not a finding
of bias or discrimination. Some reasons:

1. **Other factors.** Groups can differ in other characteristics (education,
   hours worked, age) that also relate to the outcome. A raw gap mixes all of
   these together. The prototype shows this directly: in section 3, part of
   Group B's raw gap is explained by working fewer hours.
2. **Adjusting is not neutral either.** Controlling for a variable that is
   itself shaped by group membership (for example, hours worked) can hide a
   real disparity. Whether to adjust for something is a substantive question,
   not a statistical one.
3. **How the data was collected.** Who was sampled, who responded, and how
   the outcome was recorded can all create or hide gaps.
4. **Sampling noise.** Small groups produce large gaps by chance. Group D
   in the prototype has a true effect of zero by construction yet shows an
   adjusted odds ratio of 1.64.
5. **Fairness has several definitions.** Equal outcome rates, equal error rates and
   equal calibration are different criteria that cannot generally be
   satisfied at the same time. Choosing one is a normative decision
   outside the scope of a data-quality tool.

### 1.6 Observed patterns and claims needing external context

| The tool can state (observed in this dataset) | Requires external context (the tool should not state) |
| --- | --- |
| Group B's recorded outcome rate is 31.5% vs 38.7% for Group A | The gap is caused by group membership |
| The gap is 7.2 percentage points; the intervals do not overlap | The gap is unfair, discriminatory or illegal |
| Rates differ across groups more than chance would explain (p = 0.005), but the association is weak (Cramér's V = 0.08) | A "significant" result means the gap matters in practice |
| 32 rows have no group recorded | Group B is under- or over-represented relative to the real population (needs a benchmark) |
| Group D has only 36 rows, so its rate is unstable | The same gap exists outside this sample |
| After adjusting for the listed predictors, Group B's odds ratio is 0.90 | The adjusted figure is the "true" or "fair" gap |

**Adding the representation question later** would need a user-supplied
benchmark (group → expected share, with its source and year). The measure
would be observed share − benchmark share, with the same small-group and
missing-group rules as above.

---

## 2. Regression use case

### 2.1 Outcome and approach

- **Outcome type:** binary categorical (two outcome values).
- **Approach:** logistic regression, which models the log-odds of the
  positive outcome as a linear combination of the predictors.
- **Why this case:** it pairs with the demographic question. The same outcome
  column can be studied both raw (section 1) and adjusted for other factors
  (section 2), and comparing the two is informative.
- **Why unpenalized:** the goal is interpretable coefficients, not maximum
  predictive accuracy. Regularization shrinks coefficients toward zero and
  would distort the odds ratios. The trade-off is that unpenalized fits can
  be unstable with rare categories or perfectly separating predictors (see
  section 2.7).
- A numeric outcome would use ordinary least squares with the same
  preprocessing; we propose doing one well first.

### 2.2 Outcome and candidate predictors (prototype)

| Role | Column | Type | Notes |
| --- | --- | --- | --- |
| Outcome | `high_income` | Binary 0/1 | 1% missing |
| Predictor | `age` | Numeric | |
| Predictor | `education_years` | Numeric | |
| Predictor | `hours_per_week` | Numeric | 5% missing |
| Predictor | `overtime_hours` | Numeric | Deliberately derived from `hours_per_week` to exercise the correlation review |
| Predictor | `sector` | Nominal, 4 levels | 3% missing; reference level `Private` |
| Predictor | `group` | Nominal, 4 levels | 2% missing; reference level `Group A`. Included so the adjusted group comparison can be set against the raw one |

Predictors are chosen by a person. The tool does not select them.

### 2.3 Encoding nominal categorical predictors

Nominal predictors (categories with no natural order, such as sector or
group) are **one-hot encoded with one reference level dropped**:

- Each level except the reference becomes its own 0/1 column
  (`sector_Public`, `sector_Self-employed`, …).
- The reference level is left out. Its effect is absorbed into the intercept,
  and every other level's coefficient reads as *"compared with the reference
  level, holding everything else fixed."*
- Leaving one level out is required: with all levels present the columns sum
  to 1 and duplicate the intercept, so the coefficients are not identifiable.
- **The reference level is chosen explicitly**, not alphabetically, because
  it determines what every reported comparison means. The prototype uses
  the largest or most typical level.
- **Category lists come from the training data only.** A level first seen in
  the test data is encoded as all zeros, i.e. treated like the reference level.
- **Ordinal** categories (e.g. education level as text) should not be one-hot
  encoded blindly. Whether to encode them as ordered numbers or as nominal
  categories is a per-column decision.
- Very rare levels produce unstable coefficients (see Group D below). Grouping
  them is left as a human decision.

### 2.4 Missing-value handling

| Where | Rule | Rationale |
| --- | --- | --- |
| Outcome | Row dropped before the split; count reported | The model cannot be fit or evaluated without an outcome |
| Numeric predictor | Replaced with the **training-set** median, plus a 0/1 "was missing" indicator column | Keeps rows; the indicator lets the model learn whether missingness itself relates to the outcome |
| Nominal predictor | Missing becomes its own `Missing` level | Same reasoning; also makes missingness visible in the coefficients |

Median imputation is simple and transparent, but it understates
uncertainty and can bias coefficients when values are not missing at random.
Multiple imputation would be more principled (advisor question 6).

### 2.5 How the correlation and comparison results inform predictor review

Before fitting, the existing diagnostics are run on the **training split**
to review the predictors. Each one covers a different kind of pair:

| Pair | Diagnostic | Flag | What a flag means |
| --- | --- | --- | --- |
| Numeric ~ numeric | Pearson correlation (existing `calculate_correlation_matrix`) | \|r\| ≥ 0.7 | The two carry overlapping information; their separate coefficients are unstable and should not be read on their own |
| Categorical ~ categorical | Cramér's V (Ticket #46 `compare_categorical`) | V ≥ 0.3 | Same, for categories, e.g. job title and department |
| Numeric across demographic groups | Group means/medians with Welch or Kruskal-Wallis (Ticket #46 `compare_numeric_across_groups`) | None; informational | The predictor differs by group, so adjusting for it will absorb part of the raw group gap (section 1.5, point 2) |

- Flagged predictors are **kept in the model**. Nothing is removed
  automatically.
- Predictions are usually unaffected by overlapping predictors; only the
  interpretation of their individual coefficients suffers.
- A person then decides whether to keep both, keep one, or combine them,
  based on what the columns mean.
- The third review is the one that links the regression back to the
  demographic question: it shows *which* predictors will change the group
  coefficient when included, before anyone reads that coefficient.
- **Remaining gaps:** pairwise checks miss multicollinearity involving three
  or more columns (variance inflation factors would cover this), and Pearson
  only sees straight-line relationships.

In the prototype, `hours_per_week` and `overtime_hours` are flagged
(r = 0.81). As expected, the model splits credit between them: the true
effect is +0.05 per hour on hours worked and 0 on overtime, but the estimates
are +0.071 and −0.019.

### 2.6 Evaluation approach

1. Rows with a missing outcome are removed, then the data is split **75%
   training / 25% test**, stratified so both parts have the same outcome rate.
   The split is seeded.
2. **Everything learned from data** (medians for imputation, category lists,
   the correlation review, and the coefficients) is learned from the training rows only.
   The test rows are used once, for scoring. This prevents *preprocessing
   leakage*, where information from the evaluation data leaks into the model
   and makes it look better than it is.
3. Reported metrics on the test rows:

| Metric | What it answers |
| --- | --- |
| ROC AUC | How well the model ranks positive cases above negative ones (0.5 = chance, 1.0 = perfect) |
| Brier score | Average squared error of the predicted probabilities (lower is better) |
| Accuracy at 0.5 | Share classified correctly with a 0.5 cut-off, **always shown next to** the majority-class baseline |
| Mean predicted vs observed rate | Calibration-in-the-large: does the model predict the right overall rate? |

Predictive performance is a secondary concern here. The main output is the
coefficient table. The held-out metrics are a check that the model fits the
data reasonably, not a goal in themselves.

### 2.7 Limitations

- **Association, not causation.** Coefficients describe associations in this
  data, conditional on the chosen predictors. They change if predictors are
  added or removed.
- **No uncertainty on coefficients yet.** The prototype reports point
  estimates only. Without confidence intervals, a large odds ratio from a
  small category (Group D) looks as reliable as a well-supported one. This
  should be fixed before anyone relies on the output (section 6).
- **Odds ratios are not risk ratios.** When the outcome is common (37% here),
  an odds ratio overstates the corresponding ratio of probabilities.
- **Linearity in the log-odds.** Age and hours enter as straight lines; real
  relationships may curve. Not checked in the prototype.
- **Separation.** If a category level always (or never) has the outcome, the
  unpenalized fit fails or returns extreme coefficients. Not handled yet.
- **Single split.** One 75/25 split gives one noisy estimate of performance;
  cross-validation would be steadier.
- **Survey weights ignored.** Datasets like UCI Adult carry sampling weights
  (`fnlwgt`). Unweighted results describe the sample, not the population.

---

## 3. Prototype results (synthetic data)

### 3.1 Data

2,000 synthetic rows, seed 52. Because the data was generated from known
rules, we can check the method against the truth. Built-in features:

- Group B works about 5 fewer hours per week on average **and** has a small
  direct penalty (true log-odds −0.3, i.e. odds ratio 0.74).
- Group C has a small direct advantage (+0.1, OR 1.11); Group D has none (OR 1.00).
- Group D is about 1.5% of rows, to exercise the small-group flag.
- Missing values: group 2%, hours 5%, sector 3%, outcome 1%.

No real people are represented.

### 3.2 Outcome rate by group

22 rows were excluded for a missing outcome. 32 rows had no group recorded
and are shown as their own row.

| Group | n | Share | Rate | 95% interval | Difference vs A | Ratio vs A | Notes |
| --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| Group A | 1,067 | 53.9% | 38.7% | 35.8–41.7% | — | 1.00 | reference |
| Group B | 594 | 30.0% | 31.5% | 27.9–35.3% | −7.2 pp | 0.81 | |
| Group C | 249 | 12.6% | 43.0% | 37.0–49.2% | +4.3 pp | 1.11 | |
| Group D | 36 | 1.8% | 38.9% | 24.8–55.1% | +0.2 pp | 1.00 | small group: unstable |
| (missing) | 32 | 1.6% | 40.6% | 25.5–57.7% | +1.9 pp | 1.05 | group not recorded |

**In plain language:** In this dataset, 31.5% of Group B rows have the outcome
compared with 38.7% of Group A, a gap of about 7 percentage points. Group B's
rate is about 81% of Group A's. The intervals for A and B do not overlap, so
the gap is unlikely to be sampling noise alone. Group C's rate is a few points
higher, but its interval overlaps Group A's. Group D's and the
missing-group row's intervals are so wide (roughly 25% to 55%) that no
comparison can be made. None of this says *why* the gaps exist.

**Ticket #46 comparison** on the 1,946 rows with a recorded group: chi-square
= 12.95 with 3 degrees of freedom, p = 0.005; Cramér's V = 0.08; no
expected-count warnings.

**In plain language:** the outcome rate is unlikely to be the same in every
group (p = 0.005), but group membership is only weakly associated with the
outcome overall (V = 0.08 on a 0–1 scale). The table above shows where the
difference comes from, mainly Group B. The chi-square test alone could not
say that.

### 3.3 Logistic regression

1,483 training rows, 495 test rows.

**Predictor review (training split):**

| Review | Result |
| --- | --- |
| Pearson, numeric pairs | `hours_per_week ~ overtime_hours`, r = 0.81: flagged, both kept |
| Cramér's V, `sector ~ group` | V = 0.03: not flagged (independent by construction) |
| `hours_per_week` across groups | Kruskal-Wallis H = 110.6, p < 0.001. Means: A 40.9, B 35.7, C 40.3, D 40.4 |
| `overtime_hours` across groups | H = 86.2, p < 0.001. Means: A 3.8, B 1.5, C 3.0, D 3.3 |
| `age` across groups | H = 5.8, p = 0.12. Means 42.0–45.6 |
| `education_years` across groups | H = 0.4, p = 0.93. Means 13.0–13.1 |

**In plain language:** Group B works about 5 fewer hours a week than the
other groups; age and education barely differ by group. So before reading the
model, we already expect Group B's coefficient to move toward 1 once hours are
included: some of its raw gap goes with hours worked.

| Feature | Coefficient | Odds ratio | True value (OR) | Reading |
| --- | ---: | ---: | ---: | --- |
| age (per year) | +0.040 | 1.04 | 1.04 | Each extra year: about 4% higher odds |
| education_years (per year) | +0.376 | 1.46 | 1.42 | Each extra year of education: about 46% higher odds |
| hours_per_week (per hour) | +0.071 | 1.07 | 1.05 | Shares credit with overtime (flagged pair) |
| overtime_hours (per hour) | −0.019 | 0.98 | 1.00 | Shares credit with hours (flagged pair) |
| hours missing (indicator) | +0.096 | 1.10 | 1.00 | No real effect; noise |
| sector: Public vs Private | −0.086 | 0.92 | 1.22 | |
| sector: Self-employed vs Private | +0.715 | 2.04 | 1.65 | |
| sector: Nonprofit vs Private | −0.258 | 0.77 | 0.67 | |
| sector: Missing vs Private | −0.125 | 0.88 | — | |
| group: B vs A | −0.111 | 0.90 | 0.74 | |
| group: C vs A | +0.356 | 1.43 | 1.11 | |
| group: D vs A | +0.496 | 1.64 | 1.00 | 23 training rows; unreliable |
| group: Missing vs A | −0.222 | 0.80 | — | |

| Held-out metric | Value |
| --- | --- |
| ROC AUC | 0.770 |
| Brier score | 0.185 |
| Accuracy at 0.5 | 72.7% (majority-class baseline 62.8%) |
| Mean predicted rate vs observed | 37.7% vs 37.2% |

**In plain language:**

- The model ranks cases noticeably better than chance (AUC 0.77) and predicts
  the overall rate well. It beats always guessing the most common outcome by about 10 points.
- Age and education are recovered closely. These are well-supported
  numeric predictors.
- **Raw vs adjusted, Group B:** the raw rate ratio was 0.81. After accounting
  for hours, education, age and sector, Group B's odds ratio is 0.90. This
  is the pattern the data was built with, and the one the predictor review
  predicted: part of the raw gap goes with hours worked, and part does not. The adjusted estimate (0.90) misses the
  true 0.74 by a fair margin, which shows how noisy a single sample of 2,000
  rows is. Without confidence intervals there is no way to see this from the
  output alone.
- **Group D's odds ratio of 1.64 is noise.** Its true effect is zero, and it
  has only 23 training rows. This is the strongest argument for adding
  coefficient intervals before the output is shown to anyone.
- **Sector: Public** comes out slightly below Private when the truth is
  slightly above. A modest effect on a category of about 300 training rows
  can flip sign by chance.
- **Hours and overtime:** the correlation review did its job. Individually,
  the two coefficients are misleading. Together, the hours effect is roughly
  correct. Someone reviewing the model would see the flag and could choose to
  drop `overtime_hours` for a clearer reading. The tool does not make that choice.

---

## 4. Conclusions this work does not support

- That any dataset, group or model is fair or unfair.
- That a group difference is caused by group membership.
- That an adjusted coefficient is the "real" disparity. It depends entirely on
  which predictors were included.
- That results from a sample apply to a wider population, without weights
  and a defined sampling frame.
- That a predictor should be removed because it is correlated with another.
- Anything about representation relative to a real population (no benchmark used).
- Any conclusion from groups flagged as small.

---

## 5. Questions for the advisor

1. **Question choice.** Is outcome-rate difference the right first question,
   or should representation against a benchmark come first? If the latter,
   what benchmark source would you accept for a given dataset?
2. **Small-group threshold.** Is 30 rows a sensible default for flagging, or
   should the flag depend on interval width instead?
3. **Missing outcome by group.** Should the tool also report outcome
   missingness rates per group, as a separate data-quality signal?
4. **Small-cell suppression.** For real data about people, should cells below
   some size (5? 10?) be suppressed, not just flagged?
5. **Uncertainty on coefficients.** Bootstrap intervals (no new dependency)
   or profile-likelihood intervals via `statsmodels` (new dependency)?
6. **Imputation.** Is median imputation plus a missing indicator acceptable
   for a first version, or should we use multiple imputation from the start?
7. **Adjusting for group-linked variables.** How should the documentation
   guide users on whether to adjust for variables like hours that may lie on
   the pathway from group to outcome?
8. **Real dataset.** May we run the same prototype on UCI Adult (group = `sex`
   or `race`, outcome = `income` > 50K), and should we apply `fnlwgt` as
   a weight when we do?
9. **Relationship to Ticket #46.** Should the outcome-rate view be presented
   as an extra panel on the existing #46 categorical comparison (when the
   outcome has two categories), or as a separately named analysis? The first
   keeps one place to look; the second makes the reference-group choice more
   deliberate.
10. **Association threshold.** Is Cramér's V ≥ 0.3 a reasonable point to flag
    two categorical predictors for review, given that V's scale depends on
    the number of categories?

---

## 6. Proposed next implementation scope

Subject to the answers above. Still no fair/unfair verdicts and no automatic
predictor removal.

Ticket #46 already provides most of the plumbing: stored uploads (so
comparisons can re-read the rows), an authenticated, ownership-checked
comparisons endpoint, saved results per report, and the frontend contract.
The outcome-rate measure should reuse all of it rather than add a parallel
path.

1. **Outcome-rate comparison** in `backend/diagnostics/`, built on
   `compare_categorical` as in the prototype. Run only when the user names a
   group column, binary outcome column, positive value and reference group.
   Depending on question 9, either a new `comparison_type` on
   `POST /api/reports/{id}/comparisons` or extra fields on
   `categorical_categorical` results. Not part of the default profile.
2. **Coefficient intervals** (bootstrap or `statsmodels`, per question 5),
   with small-sample warnings on rare levels.
3. **Predictor review as a single call**, wrapping Pearson, the #46
   comparisons and VIF, still advisory only.
4. **Separation and convergence checks**, with a plain-language error rather
   than extreme coefficients.
5. **Optional representation measure**, only when the user supplies a
   benchmark table with source and year.
6. Unit tests on small hand-calculated cases (as in the prototype tests) and
   one `integration` test on UCI Adult, if approved.

Out of scope until reviewed: regression endpoints and dashboard views.

---

## How to reproduce

From the repository root, on `main` after PR #94 (Ticket #46) is merged, with
`backend/requirements.txt` installed:

```bash
python -m research.demographic_regression_prototype
python -m pytest test/test_demographic_regression_prototype.py
```

The data, the split and the model are all seeded (seed 52). The printed output
was confirmed identical on scikit-learn 1.6.0 and 1.9.1.
