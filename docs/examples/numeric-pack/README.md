# Numeric analysis demo pack (Ticket #57)

Small synthetic datasets, runnable requests, expected results and real responses for
Welch's t-test, Welch's ANOVA, Kruskal-Wallis and distribution-shape descriptions.

* `datasets/` - the CSV files.
* `cases.json` - every case, with expected values calculated directly with pandas and
  scipy (never with the backend). Numeric tolerance: relative 1e-6, absolute 1e-9;
  counts and labels must match exactly.
* `responses/` - the real API response for each case (success, warning and unavailable
  examples for Tickets #47 and #55).

Rebuild everything with `python scripts/build_numeric_pack.py` (needs scipy >= 1.16 for
`f_oneway(equal_var=False)`). `python -m pytest test/test_numeric_pack.py` runs every case
through the API, checks it against `cases.json`, checks saved results reopen unchanged,
and checks `responses/` still match the endpoint.

## Run it by hand

Start the backend (`./run-all.sh` or `uvicorn backend.api.main:app`), then from this folder:

```bash
python ../../../scripts/dev_seed.py   # creates dev1@example.com / devpassword1
curl -c jar.txt -H 'Content-Type: application/json' -d '{"email":"dev1@example.com","password":"devpassword1"}' http://127.0.0.1:8000/api/auth/login
ID=$(curl -s -b jar.txt -F file=@datasets/departments.csv http://127.0.0.1:8000/api/analyze | python -c 'import json,sys; print(json.load(sys.stdin)["analysis_id"])')
```

Each case below gives its own upload and request. Afterwards:

```bash
curl -b jar.txt http://127.0.0.1:8000/api/reports/$ID/comparisons                 # saved results, with method and evidence
curl -b jar.txt http://127.0.0.1:8000/api/reports/$ID                             # column_profiles[].distribution_shape
curl -b jar.txt -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8000/api/reports/$ID/suggestions   # Ticket #47
```

## Demo script

1. Upload `two_groups.csv` and run **two_groups_known_difference**: Welch's t-test, the mean
   difference (control minus treatment, about -5) and its 95% confidence interval.
2. Upload `departments.csv` and run **anova_unequal_groups**: Welch's ANOVA with F, both
   degrees of freedom, eta squared and the small-group warning. Then run
   **auto_three_groups_rank_based** to show the default stays the rank-based Kruskal-Wallis.
3. Upload `shapes.csv` and open the report: each numeric profile has `distribution_shape`
   next to the unchanged `histogram`.
4. `GET .../comparisons` reopens the saved results unchanged. Each group carries count,
   mean, median, SD, quartiles, whiskers and outlier counts for the charts; `POST
   .../suggestions` explains them without recalculating anything.

## Cases

### two_groups_known_difference (success)

**Two independent groups with a known mean difference.** Is the mean score different for control and treatment?

* Dataset: `datasets/two_groups.csv`
* Columns: group_column = `group`, value_column = `score`
* Request:

  ```bash
  curl -b jar.txt -H 'Content-Type: application/json' -d '{"comparison_type": "categorical_numeric", "group_column": "group", "value_column": "score", "method": "welch_t_test"}' http://127.0.0.1:8000/api/reports/$ID/comparisons
  ```

* Expected HTTP status: 201
* Expected: `rows.included` = 75; `test.status` = "ok"; `test.statistic` = -2.55; `test.degrees_of_freedom` = 72.84; `test.p_value` = 0.01286; `test.mean_difference` = -5; `test.mean_difference_ci.lower` = -8.908; `test.mean_difference_ci.upper` = -1.093. Group summaries are in `cases.json`.
* No warning containing: "fewer than 30"
* Supports: Per-group mean chart with the mean difference and its 95% confidence interval; grouped box plot.
* Notes: Groups were generated with means of exactly 50 and 55 (difference -5 after rounding to 3 decimals: control minus treatment). Both groups have at least 30 rows, so no warnings.
* Real response: `responses/two_groups_known_difference.json`

### anova_unequal_groups (warning)

**Welch's ANOVA across four groups of unequal size and spread.** Does mean weekly hours differ across departments?

* Dataset: `datasets/departments.csv`
* Columns: group_column = `department`, value_column = `hours`
* Request:

  ```bash
  curl -b jar.txt -H 'Content-Type: application/json' -d '{"comparison_type": "categorical_numeric", "group_column": "department", "value_column": "hours", "method": "welch_anova"}' http://127.0.0.1:8000/api/reports/$ID/comparisons
  ```

* Expected HTTP status: 201
* Expected: `rows.included` = 117; `test.status` = "ok"; `test.statistic` = 7.358; `test.degrees_of_freedom_between` = 3; `test.p_value` = 0.0004633; `test.eta_squared` = 0.1544. Group summaries are in `cases.json`.
* Warning contains: "fewer than 30"
* Supports: Group summary table and grouped box plot of hours by department; eta squared beside it.
* Notes: Sizes 50/35/20/12 with standard deviations 4/6/9/3, the case Welch's ANOVA is for. C and D have fewer than 30 rows, so a normality warning is returned. The test does not say which departments differ.
* Real response: `responses/anova_unequal_groups.json`

### auto_three_groups_rank_based (success)

**Default method for three or more groups stays Kruskal-Wallis.** Same selection without a method: do hours tend to be higher in some departments?

* Dataset: `datasets/departments.csv`
* Columns: group_column = `department`, value_column = `hours`
* Request:

  ```bash
  curl -b jar.txt -H 'Content-Type: application/json' -d '{"comparison_type": "categorical_numeric", "group_column": "department", "value_column": "hours"}' http://127.0.0.1:8000/api/reports/$ID/comparisons
  ```

* Expected HTTP status: 201
* Expected: `rows.included` = 117; `test.status` = "ok"; `test.statistic` = 20.19; `test.degrees_of_freedom` = 3; `test.p_value` = 0.0001549. Group summaries are in `cases.json`.
* No warning containing: "fewer than 5"
* Supports: Grouped box plot; label the result as a rank comparison, not a comparison of means.
* Notes: Existing requests without `method` keep the Ticket #51 behaviour; analysis_question.key is compare_ranks.
* Real response: `responses/auto_three_groups_rank_based.json`

### anova_no_strong_evidence (warning)

**Comparison without strong evidence of a difference.** Does mean satisfaction differ across departments?

* Dataset: `datasets/departments.csv`
* Columns: group_column = `department`, value_column = `satisfaction`
* Request:

  ```bash
  curl -b jar.txt -H 'Content-Type: application/json' -d '{"comparison_type": "categorical_numeric", "group_column": "department", "value_column": "satisfaction", "method": "welch_anova"}' http://127.0.0.1:8000/api/reports/$ID/comparisons
  ```

* Expected HTTP status: 201
* Expected: `rows.included` = 117; `test.status` = "ok"; `test.statistic` = 1.262; `test.degrees_of_freedom_between` = 3; `test.p_value` = 0.2996; `test.eta_squared` = 0.01667. Group summaries are in `cases.json`.
* Warning contains: "fewer than 30"
* Supports: Per-group means with overlapping spreads.
* Notes: All departments were drawn from the same distribution. A large p-value is not proof the departments are equal; the method's limitations say so.
* Real response: `responses/anova_no_strong_evidence.json`

### missing_and_non_finite (warning)

**Missing group labels and missing, NaN and infinite measurements.** Does the mean reading differ between sites, once unusable rows are left out?

* Dataset: `datasets/messy.csv`
* Columns: group_column = `site`, value_column = `reading`
* Request:

  ```bash
  curl -b jar.txt -H 'Content-Type: application/json' -d '{"comparison_type": "categorical_numeric", "group_column": "site", "value_column": "reading", "method": "welch_t_test"}' http://127.0.0.1:8000/api/reports/$ID/comparisons
  ```

* Expected HTTP status: 201
* Expected: `rows.included` = 23; `test.status` = "ok"; `test.statistic` = -0.8243; `test.degrees_of_freedom` = 18.4; `test.p_value` = 0.4203; `test.mean_difference` = -1.231; `test.mean_difference_ci.lower` = -4.364; `test.mean_difference_ci.upper` = 1.902. Group summaries are in `cases.json`.
* Warning contains: "fewer than 30"
* Supports: Group summary table with included and excluded row counts.
* Notes: Row 3 is missing both values and is counted under both reasons; excluded rows are counted once.
* Real response: `responses/missing_and_non_finite.json`

### anova_constant_values (unavailable)

**Constant measurement.** Does the mean of a constant column differ across teams?

* Dataset: `datasets/constant.csv`
* Columns: group_column = `team`, value_column = `fixed`
* Request:

  ```bash
  curl -b jar.txt -H 'Content-Type: application/json' -d '{"comparison_type": "categorical_numeric", "group_column": "team", "value_column": "fixed", "method": "welch_anova"}' http://127.0.0.1:8000/api/reports/$ID/comparisons
  ```

* Expected HTTP status: 201
* Expected: `rows.included` = 15; `test.status` = "unavailable". Group summaries are in `cases.json`.
* Unavailable reason contains: "zero variance"
* Supports: Group summary table only; no test result.
* Notes: Every group has zero variance, so Welch's weights are undefined. Summaries are still returned.
* Real response: `responses/anova_constant_values.json`

### welch_insufficient_observations (unavailable)

**Group with a single observation.** Is the mean spread different for the solo row and the rest?

* Dataset: `datasets/constant.csv`
* Columns: group_column = `pair_group`, value_column = `spread`
* Request:

  ```bash
  curl -b jar.txt -H 'Content-Type: application/json' -d '{"comparison_type": "categorical_numeric", "group_column": "pair_group", "value_column": "spread", "method": "welch_t_test"}' http://127.0.0.1:8000/api/reports/$ID/comparisons
  ```

* Expected HTTP status: 201
* Expected: `rows.included` = 15; `test.status` = "unavailable". Group summaries are in `cases.json`.
* Unavailable reason contains: "at least two values"
* Supports: Group summary table only; no test result or confidence interval.
* Notes: A group of one has no standard deviation, so the t-test and interval cannot be calculated.
* Real response: `responses/welch_insufficient_observations.json`

### anova_with_two_groups (unavailable)

**Method that does not fit the number of groups.** Welch's ANOVA requested for two groups.

* Dataset: `datasets/two_groups.csv`
* Columns: group_column = `group`, value_column = `score`
* Request:

  ```bash
  curl -b jar.txt -H 'Content-Type: application/json' -d '{"comparison_type": "categorical_numeric", "group_column": "group", "value_column": "score", "method": "welch_anova"}' http://127.0.0.1:8000/api/reports/$ID/comparisons
  ```

* Expected HTTP status: 201
* Expected: `rows.included` = 75; `test.status` = "unavailable". Group summaries are in `cases.json`.
* Unavailable reason contains: "welch_t_test"
* Supports: Prompt the user to switch to Welch's t-test.
* Notes: Welch's ANOVA is offered for three or more groups; the reason points to welch_t_test.
* Real response: `responses/anova_with_two_groups.json`

### shape_right_skewed (success)

**Right-skewed distribution.** What is the shape of the 'right_skewed' distribution?

* Dataset: `datasets/shapes.csv`
* Columns: column = `right_skewed`
* Request: `curl -b jar.txt http://127.0.0.1:8000/api/reports/$ID` and read the `right_skewed` entry of `column_profiles`.
* Expected: `distribution_shape.status` = "ok"; `distribution_shape.skewness` = 1.633; `distribution_shape.classification` = "right_skewed"; `distribution_shape.strength` = "strong"; `distribution_shape.sample_size` = 300. Group summaries are in `cases.json`.
* Supports: Histogram with 'strongly right-skewed' beside it.
* Notes: Log-normal values: a long tail of large values.
* Real response: `responses/shape_right_skewed.json`

### shape_left_skewed (success)

**Left-skewed distribution.** What is the shape of the 'left_skewed' distribution?

* Dataset: `datasets/shapes.csv`
* Columns: column = `left_skewed`
* Request: `curl -b jar.txt http://127.0.0.1:8000/api/reports/$ID` and read the `left_skewed` entry of `column_profiles`.
* Expected: `distribution_shape.status` = "ok"; `distribution_shape.skewness` = -1.633; `distribution_shape.classification` = "left_skewed"; `distribution_shape.strength` = "strong"; `distribution_shape.sample_size` = 300. Group summaries are in `cases.json`.
* Supports: Histogram with 'strongly left-skewed' beside it.
* Notes: The mirror image of right_skewed, so the skewness has the same size and opposite sign.
* Real response: `responses/shape_left_skewed.json`

### shape_symmetric (success)

**Approximately symmetric distribution.** What is the shape of the 'symmetric' distribution?

* Dataset: `datasets/shapes.csv`
* Columns: column = `symmetric`
* Request: `curl -b jar.txt http://127.0.0.1:8000/api/reports/$ID` and read the `symmetric` entry of `column_profiles`.
* Expected: `distribution_shape.status` = "ok"; `distribution_shape.skewness` = 0.09105; `distribution_shape.classification` = "approximately_symmetric"; `distribution_shape.strength` = null; `distribution_shape.sample_size` = 300. Group summaries are in `cases.json`.
* Supports: Histogram with 'approximately symmetric'; do not call it normal.
* Notes: Normal draws. Approximate symmetry is reported, never normality.
* Real response: `responses/shape_symmetric.json`

### shape_constant (unavailable)

**Constant column.** What is the shape of the 'fixed' distribution?

* Dataset: `datasets/constant.csv`
* Columns: column = `fixed`
* Request: `curl -b jar.txt http://127.0.0.1:8000/api/reports/$ID` and read the `fixed` entry of `column_profiles`.
* Expected: `distribution_shape.status` = "unavailable"; `distribution_shape.skewness` = null; `distribution_shape.sample_size` = 15. Group summaries are in `cases.json`.
* Unavailable reason contains: "identical"
* Supports: Histogram of a single bar; no shape description.
* Notes: Skewness is undefined with no spread.
* Real response: `responses/shape_constant.json`

### shape_insufficient (unavailable)

**Too few observations.** What is the shape of the 'rare' distribution?

* Dataset: `datasets/constant.csv`
* Columns: column = `rare`
* Request: `curl -b jar.txt http://127.0.0.1:8000/api/reports/$ID` and read the `rare` entry of `column_profiles`.
* Expected: `distribution_shape.status` = "unavailable"; `distribution_shape.skewness` = null; `distribution_shape.sample_size` = 2. Group summaries are in `cases.json`.
* Unavailable reason contains: "at least 3"
* Supports: No shape description.
* Notes: Only 2 finite values; at least 3 are needed.
* Real response: `responses/shape_insufficient.json`

### shape_small_sample (warning)

**Small sample.** What is the shape of the 'spread' distribution?

* Dataset: `datasets/constant.csv`
* Columns: column = `spread`
* Request: `curl -b jar.txt http://127.0.0.1:8000/api/reports/$ID` and read the `spread` entry of `column_profiles`.
* Expected: `distribution_shape.status` = "ok"; `distribution_shape.skewness` = 0.4639; `distribution_shape.classification` = "approximately_symmetric"; `distribution_shape.strength` = null; `distribution_shape.sample_size` = 15. Group summaries are in `cases.json`.
* `distribution_shape.warnings` says the estimate is unstable.
* Supports: Histogram with the shape marked as tentative.
* Notes: 15 values: the description is returned with an instability warning.
* Real response: `responses/shape_small_sample.json`
