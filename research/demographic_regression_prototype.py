"""
Ticket #52: research prototype for one demographic measure and one regression.

Not a production diagnostic. Nothing here is wired into the API, the database
or the report schema. The design write-up that explains every choice made here
is docs/demographic_bias_and_regression_design.md.

Run from the repo root:
    python -m research.demographic_regression_prototype

Everything is seeded, so the printed numbers are identical on every run.

Analysis question:
    Does the observed rate of a binary outcome differ between groups of one
    demographic column, relative to a chosen reference group?

Regression use case:
    Binary outcome -> logistic regression. Nominal predictors are one-hot
    encoded against an explicit reference level, and all preprocessing is fit
    on the training split only.

Depends on the Ticket #46 comparisons (PR #94): the rate table is derived
from compare_categorical's contingency table, and the predictor review uses
compare_categorical and compare_numeric_across_groups next to the Pearson
matrix.
"""

from math import sqrt

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from backend.diagnostics.categorical_comparison import compare_categorical
from backend.diagnostics.correlation_analysis import calculate_correlation_matrix
from backend.diagnostics.numeric_group_comparison import compare_numeric_across_groups

RANDOM_SEED = 52

# Groups with fewer rows than this are reported but flagged as unstable.
MIN_GROUP_SIZE = 30

# Label used when the group column itself is missing. Kept as its own row so
# missing demographics are visible instead of silently dropped.
MISSING_GROUP_LABEL = "(missing)"

# Label used when a nominal predictor is missing. Encoded like any category.
MISSING_CATEGORY_LABEL = "Missing"

# Absolute Pearson r at or above this is surfaced for review, never removed.
CORRELATION_REVIEW_THRESHOLD = 0.7

# Cramér's V at or above this between two nominal predictors is surfaced for
# review, never removed.
ASSOCIATION_REVIEW_THRESHOLD = 0.3

# z for a 95% Wilson interval.
_Z_95 = 1.959963984540054


# ---------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------

def make_synthetic_dataset(n_rows: int = 2000, seed: int = RANDOM_SEED) -> pd.DataFrame:
    """Adult-shaped synthetic data with known structure and no real people.

    The outcome is generated from known coefficients, so the regression output
    can be checked against the truth. Group B works fewer hours on average and
    has a small direct penalty, so part of its rate gap is explained by hours
    and part is not. Group D is deliberately tiny to exercise the small-group
    flag. overtime_hours is built from hours_per_week so the correlation
    review has something to flag.
    """
    rng = np.random.default_rng(seed)

    group = rng.choice(
        ["Group A", "Group B", "Group C", "Group D"],
        size=n_rows,
        p=[0.55, 0.30, 0.135, 0.015],
    )
    age = rng.integers(18, 71, size=n_rows)
    education_years = np.clip(rng.normal(13, 2.5, size=n_rows).round(), 6, 20)

    base_hours = np.where(group == "Group B", 36.0, 41.0)
    hours_per_week = np.clip(rng.normal(base_hours, 8.0), 5, 80).round()
    overtime_hours = np.clip(hours_per_week - 40 + rng.normal(0, 2.0, n_rows), 0, None).round()

    sector = rng.choice(
        ["Private", "Public", "Self-employed", "Nonprofit"],
        size=n_rows,
        p=[0.6, 0.2, 0.12, 0.08],
    )

    sector_effect = pd.Series(sector).map(
        {"Private": 0.0, "Public": 0.2, "Self-employed": 0.5, "Nonprofit": -0.4}
    ).to_numpy()
    group_effect = pd.Series(group).map(
        {"Group A": 0.0, "Group B": -0.3, "Group C": 0.1, "Group D": 0.0}
    ).to_numpy()
    log_odds = (
        -9.0
        + 0.04 * age
        + 0.35 * education_years
        + 0.05 * hours_per_week
        + sector_effect
        + group_effect
    )
    probability = 1.0 / (1.0 + np.exp(-log_odds))
    high_income = (rng.random(n_rows) < probability).astype(int)

    df = pd.DataFrame(
        {
            "group": group,
            "age": age,
            "education_years": education_years,
            "hours_per_week": hours_per_week,
            "overtime_hours": overtime_hours,
            "sector": sector,
            "high_income": high_income,
        }
    )

    # Inject missing values at known rates so the reporting can be checked.
    df.loc[rng.random(n_rows) < 0.02, "group"] = np.nan
    df.loc[rng.random(n_rows) < 0.05, "hours_per_week"] = np.nan
    df.loc[rng.random(n_rows) < 0.03, "sector"] = np.nan
    df["high_income"] = df["high_income"].astype("float64")
    df.loc[rng.random(n_rows) < 0.01, "high_income"] = np.nan

    return df


# ---------------------------------------------------------------------------
# Demographic measure: outcome-rate differences between groups
# ---------------------------------------------------------------------------

def wilson_interval(successes: int, n: int, z: float = _Z_95) -> tuple:
    """95% Wilson score interval for a proportion. (None, None) when n is 0."""
    if n == 0:
        return (None, None)
    p = successes / n
    denominator = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denominator
    half_width = z * sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator
    return (max(0.0, centre - half_width), min(1.0, centre + half_width))


def _independence_test(groups: pd.Series, outcomes: pd.Series,
                       group_column: str, outcome_column: str) -> dict:
    """The #46 chi-square test and Cramér's V, condensed for printing."""
    comparison = compare_categorical(
        pd.DataFrame({group_column: groups, outcome_column: outcomes}),
        group_column,
        outcome_column,
    )
    test, association = comparison["test"], comparison["association"]
    return {
        "rows_included": comparison["rows"]["included"],
        "status": test["status"],
        "reason": test["reason"],
        "chi_square": test.get("statistic"),
        "degrees_of_freedom": test.get("degrees_of_freedom"),
        "p_value": test.get("p_value"),
        "cramers_v": association.get("value"),
        "warnings": comparison["warnings"],
    }


def outcome_rate_by_group(
    df: pd.DataFrame,
    group_column: str,
    outcome_column: str,
    reference_group: str,
    positive_value=1,
    min_group_size: int = MIN_GROUP_SIZE,
) -> dict:
    """Positive-outcome rate per group, compared to one reference group.

    A thin layer over the Ticket #46 contingency table: counts come from
    compare_categorical, and this adds the reference comparison, intervals
    and flags. Outcomes stored as 0/1 numbers are treated as categories.

    Rows with a missing outcome are excluded from every rate and counted in
    'excluded_missing_outcome'. Rows with a missing group stay in as their
    own MISSING_GROUP_LABEL row. Groups below min_group_size keep their
    numbers but are flagged 'small_group'.

    Differences are percentage points (group minus reference). Ratios are
    group rate over reference rate, None when the reference rate is 0.

    'independence_test' is the #46 chi-square test and Cramér's V on the rows
    with a recorded group, i.e. what the comparisons API shows for the same
    two columns.
    """
    if group_column not in df.columns:
        raise KeyError(group_column)
    if outcome_column not in df.columns:
        raise KeyError(outcome_column)

    groups_raw = df[group_column].astype(object)
    outcomes = df[outcome_column].astype(object)
    labelled = pd.DataFrame(
        {
            group_column: groups_raw.where(groups_raw.notna(), MISSING_GROUP_LABEL),
            outcome_column: outcomes,
        }
    )
    table = compare_categorical(labelled, group_column, outcome_column)
    if table["status"] != "ok":
        raise ValueError(table["reason"])
    if len(table["outcome_categories"]) > 2:
        raise ValueError(
            f"Outcome column {outcome_column!r} has {len(table['outcome_categories'])} "
            "categories; this measure needs a binary outcome."
        )
    if reference_group not in table["group_categories"]:
        raise ValueError(f"Reference group {reference_group!r} has no rows with an outcome.")

    outcome_labels = table["outcome_categories"]
    positive_index = (
        outcome_labels.index(positive_value) if positive_value in outcome_labels else None
    )
    scored_rows = table["rows"]["included"]
    counts = {
        label: (
            int(total),
            int(row[positive_index]) if positive_index is not None else 0,
        )
        for label, total, row in zip(
            table["group_categories"], table["group_totals"], table["counts"]
        )
    }
    reference_n, reference_positives = counts[reference_group]
    reference_rate = reference_positives / reference_n

    groups = []
    # Already ordered by descending count, then label, by compare_categorical.
    for label, (n, positives) in counts.items():
        rate = positives / n
        low, high = wilson_interval(positives, n)
        is_reference = label == reference_group
        groups.append(
            {
                "group": str(label),
                "n": n,
                "share_of_scored_rows": 100.0 * n / scored_rows,
                "positives": positives,
                "rate": 100.0 * rate,
                "rate_ci_95": [100.0 * low, 100.0 * high],
                "difference_vs_reference_pp": 0.0 if is_reference else 100.0 * (rate - reference_rate),
                "ratio_vs_reference": (
                    1.0 if is_reference
                    else (rate / reference_rate if reference_rate > 0 else None)
                ),
                "is_reference": is_reference,
                "small_group": n < min_group_size,
                "is_missing_group": label == MISSING_GROUP_LABEL,
            }
        )

    return {
        "group_column": group_column,
        "outcome_column": outcome_column,
        "positive_value": positive_value,
        "reference_group": reference_group,
        "total_rows": table["rows"]["total"],
        "excluded_missing_outcome": table["rows"]["exclusion_reasons"]["missing_outcome_value"],
        "rows_with_missing_group": counts.get(MISSING_GROUP_LABEL, (0, 0))[0],
        "independence_test": _independence_test(groups_raw, outcomes, group_column, outcome_column),
        "min_group_size": min_group_size,
        "groups": groups,
    }


# ---------------------------------------------------------------------------
# Regression: binary outcome -> logistic regression
# ---------------------------------------------------------------------------

def _categories_with_reference_first(series: pd.Series, reference: str) -> list:
    """Sorted training categories with the reference level moved to the front."""
    values = series.fillna(MISSING_CATEGORY_LABEL).astype(str)
    categories = sorted(set(values))
    if reference not in categories:
        raise ValueError(f"Reference level {reference!r} not present in training data.")
    categories.remove(reference)
    return [reference] + categories


def build_logistic_pipeline(
    train_df: pd.DataFrame,
    numeric_predictors: list,
    nominal_predictors: dict,
) -> Pipeline:
    """Preprocessing + unpenalized logistic regression, unfitted.

    nominal_predictors maps column -> reference level. Category lists come
    from train_df only, so test-set categories never shape the encoding.

    Numeric: median imputation plus a 0/1 missing indicator, raw units kept
    so coefficients read as "per year", "per hour".
    Nominal: missing becomes its own 'Missing' level, then one-hot with the
    reference level dropped. A level first seen at prediction time encodes as
    all zeros, i.e. it is treated like the reference level.
    """
    nominal_columns = list(nominal_predictors)
    categories = [
        _categories_with_reference_first(train_df[column], reference)
        for column, reference in nominal_predictors.items()
    ]

    numeric_steps = Pipeline(
        [("impute", SimpleImputer(strategy="median", add_indicator=True))]
    )
    nominal_steps = Pipeline(
        [
            ("fill", SimpleImputer(strategy="constant", fill_value=MISSING_CATEGORY_LABEL)),
            (
                "one_hot",
                OneHotEncoder(categories=categories, drop="first", handle_unknown="ignore"),
            ),
        ]
    )
    preprocess = ColumnTransformer(
        [
            ("numeric", numeric_steps, numeric_predictors),
            ("nominal", nominal_steps, nominal_columns),
        ],
        verbose_feature_names_out=False,
    )
    return Pipeline(
        [
            ("preprocess", preprocess),
            # C=inf is unpenalized (penalty=None is deprecated from 1.8). The
            # tight tol makes coefficients agree across scikit-learn versions.
            ("model", LogisticRegression(C=np.inf, tol=1e-10, max_iter=10000)),
        ]
    )


def _as_text(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    """Cast nominal columns to object strings, keeping NaN as NaN."""
    out = df.copy()
    for column in columns:
        out[column] = out[column].astype(object).where(out[column].notna(), np.nan)
    return out


def correlation_review(train_df: pd.DataFrame, numeric_predictors: list,
                       threshold: float = CORRELATION_REVIEW_THRESHOLD) -> list:
    """Numeric predictor pairs with |r| >= threshold, from the existing diagnostic.

    Uses the training split only. Pairs are surfaced for a human decision;
    nothing is dropped from the model.
    """
    result = calculate_correlation_matrix(train_df[numeric_predictors])
    columns = result["columns"]
    flagged = []
    for i, left in enumerate(columns):
        for j in range(i + 1, len(columns)):
            r = result["matrix"][i][j]
            if r is not None and abs(r) >= threshold:
                flagged.append({"pair": [left, columns[j]], "pearson_r": r})
    return flagged


def predictor_review(train_df: pd.DataFrame, numeric_predictors: list,
                     nominal_predictors: list, group_column: str = None) -> dict:
    """Advisory review of the predictors on the training split. Removes nothing.

    numeric_pairs:  Pearson |r| >= CORRELATION_REVIEW_THRESHOLD (existing diagnostic).
    nominal_pairs:  Cramér's V for every pair of nominal predictors, from the
                    #46 categorical comparison; 'flagged' at
                    ASSOCIATION_REVIEW_THRESHOLD.
    numeric_by_group: each numeric predictor summarised across group_column,
                    from the #46 numeric comparison. A predictor that differs
                    by group will absorb part of the raw group gap once the
                    model adjusts for it.
    """
    nominal_pairs = []
    for i, left in enumerate(nominal_predictors):
        for right in nominal_predictors[i + 1:]:
            comparison = compare_categorical(train_df, left, right)
            v = comparison["association"]["value"] if comparison["association"] else None
            nominal_pairs.append(
                {
                    "pair": [left, right],
                    "cramers_v": v,
                    "flagged": v is not None and v >= ASSOCIATION_REVIEW_THRESHOLD,
                    "warnings": comparison["warnings"],
                }
            )

    numeric_by_group = []
    if group_column is not None:
        for column in numeric_predictors:
            comparison = compare_numeric_across_groups(train_df, group_column, column)
            test = comparison["test"]
            numeric_by_group.append(
                {
                    "value_column": column,
                    "test": test["method"]["name"],
                    "statistic_name": test.get("statistic_name"),
                    "statistic": test.get("statistic"),
                    "p_value": test.get("p_value"),
                    "group_means": {g["label"]: g["mean"] for g in comparison["groups"]},
                    "group_medians": {g["label"]: g["median"] for g in comparison["groups"]},
                    "warnings": comparison["warnings"],
                }
            )

    return {
        "numeric_pairs": correlation_review(train_df, numeric_predictors),
        "nominal_pairs": nominal_pairs,
        "numeric_by_group": numeric_by_group,
    }


def fit_logistic_example(
    df: pd.DataFrame,
    outcome_column: str,
    numeric_predictors: list,
    nominal_predictors: dict,
    group_column: str = None,
    test_size: float = 0.25,
    seed: int = RANDOM_SEED,
) -> dict:
    """Split, fit on train, evaluate on held-out test. Returns a plain dict.

    Rows with a missing outcome are dropped before the split (and counted).
    The split is stratified on the outcome. Every learned quantity (medians,
    category lists, coefficients, the predictor review) comes from the
    training rows only. group_column, if given, must be one of the nominal
    predictors; numeric predictors are then summarised across its groups.
    """
    predictors = list(numeric_predictors) + list(nominal_predictors)
    has_outcome = df[outcome_column].notna()
    usable = _as_text(df.loc[has_outcome], list(nominal_predictors))
    y = usable[outcome_column].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        usable[predictors], y, test_size=test_size, random_state=seed, stratify=y
    )

    review = predictor_review(
        X_train, numeric_predictors, list(nominal_predictors), group_column
    )

    pipeline = build_logistic_pipeline(X_train, numeric_predictors, nominal_predictors)
    pipeline.fit(X_train, y_train)

    feature_names = pipeline.named_steps["preprocess"].get_feature_names_out()
    model = pipeline.named_steps["model"]
    coefficients = [
        {
            "feature": str(name),
            "coefficient": float(coef),
            "odds_ratio": float(np.exp(coef)),
        }
        for name, coef in zip(feature_names, model.coef_[0])
    ]

    probabilities = pipeline.predict_proba(X_test)[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    majority_class = int(y_train.mode()[0])

    return {
        "outcome_column": outcome_column,
        "rows_dropped_missing_outcome": int((~has_outcome).sum()),
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "train_positive_rate": 100.0 * float(y_train.mean()),
        "reference_levels": dict(nominal_predictors),
        "intercept": float(model.intercept_[0]),
        "coefficients": coefficients,
        "predictor_review": review,
        "evaluation": {
            "roc_auc": float(roc_auc_score(y_test, probabilities)),
            "brier_score": float(brier_score_loss(y_test, probabilities)),
            "accuracy_at_0_5": float(accuracy_score(y_test, predictions)),
            "majority_class_accuracy": float((y_test == majority_class).mean()),
            "mean_predicted_rate": 100.0 * float(probabilities.mean()),
            "observed_test_rate": 100.0 * float(y_test.mean()),
        },
    }


# ---------------------------------------------------------------------------
# Plain-language output
# ---------------------------------------------------------------------------

def _print_rate_report(report: dict) -> None:
    print("=" * 78)
    print("1. DEMOGRAPHIC MEASURE: outcome rate by group")
    print("=" * 78)
    print(
        f"Question: is the observed rate of {report['outcome_column']} = "
        f"{report['positive_value']} different across '{report['group_column']}', "
        f"compared with '{report['reference_group']}'?"
    )
    print(
        f"Rows: {report['total_rows']}; excluded for missing outcome: "
        f"{report['excluded_missing_outcome']}; missing group (kept as its own row): "
        f"{report['rows_with_missing_group']}."
    )
    print()
    print(f"{'group':<12}{'n':>6}{'share%':>8}{'rate%':>8}{'95% CI':>17}{'diff pp':>9}{'ratio':>7}  notes")
    for g in report["groups"]:
        low, high = g["rate_ci_95"]
        ratio = "-" if g["ratio_vs_reference"] is None else f"{g['ratio_vs_reference']:.2f}"
        notes = []
        if g["is_reference"]:
            notes.append("reference")
        if g["small_group"]:
            notes.append(f"small group (<{report['min_group_size']}): unstable")
        if g["is_missing_group"]:
            notes.append("group not recorded")
        print(
            f"{g['group']:<12}{g['n']:>6}{g['share_of_scored_rows']:>8.1f}{g['rate']:>8.1f}"
            f"{f'[{low:.1f}, {high:.1f}]':>17}{g['difference_vs_reference_pp']:>+9.1f}{ratio:>7}  "
            f"{'; '.join(notes)}"
        )
    print()
    t = report["independence_test"]
    print(f"Ticket #46 comparison on the {t['rows_included']} rows with a recorded group:")
    if t["status"] == "ok":
        print(
            f"  chi-square = {t['chi_square']:.2f}, df = {t['degrees_of_freedom']}, "
            f"p = {t['p_value']:.2g}; Cramer's V = {t['cramers_v']:.3f}"
        )
    else:
        print(f"  unavailable: {t['reason']}")
    for warning in t["warnings"]:
        print(f"  warning: {warning}")
    print()
    print("Reading it: 'diff pp' is the gap in percentage points from the reference")
    print("group; 'ratio' is the group's rate divided by the reference rate. The")
    print("chi-square p-value says whether the rates differ more than chance would")
    print("explain; Cramer's V says how strongly (0 = not at all). These are observed")
    print("differences in this dataset only. They do not say why the gap exists or")
    print("whether it is unfair; see the design document, section 1.5.")


def _print_regression_report(result: dict) -> None:
    print()
    print("=" * 78)
    print("2. REGRESSION: logistic regression for a binary outcome")
    print("=" * 78)
    print(
        f"Outcome: {result['outcome_column']}. Train rows: {result['train_rows']}, "
        f"held-out test rows: {result['test_rows']}, dropped for missing outcome: "
        f"{result['rows_dropped_missing_outcome']}."
    )
    print(f"Reference levels for categorical predictors: {result['reference_levels']}")
    print()
    review = result["predictor_review"]
    print("Predictor review (training split; advisory, nothing is removed):")
    print(f"  Numeric pairs, Pearson |r| >= {CORRELATION_REVIEW_THRESHOLD}:")
    if review["numeric_pairs"]:
        for item in review["numeric_pairs"]:
            a, b = item["pair"]
            print(f"    {a} ~ {b}: r = {item['pearson_r']:.2f}  -> flagged for review, kept in model")
    else:
        print("    none")
    print(f"  Nominal pairs, Cramer's V (flag at >= {ASSOCIATION_REVIEW_THRESHOLD}):")
    for item in review["nominal_pairs"]:
        a, b = item["pair"]
        v = "unavailable" if item["cramers_v"] is None else f"{item['cramers_v']:.3f}"
        flag = "  -> flagged for review, kept in model" if item["flagged"] else ""
        print(f"    {a} ~ {b}: V = {v}{flag}")
        for warning in item["warnings"]:
            print(f"      warning: {warning}")
    if review["numeric_by_group"]:
        print("  Numeric predictors across groups (mean per group):")
        for item in review["numeric_by_group"]:
            means = ", ".join(
                f"{label} {mean:.1f}" for label, mean in item["group_means"].items()
            )
            print(
                f"    {item['value_column']}: {item['statistic_name']} = "
                f"{item['statistic']:.1f}, p = {item['p_value']:.2g}  [{means}]"
            )
    print()
    print(f"{'feature':<32}{'coef':>9}{'odds ratio':>12}")
    for c in result["coefficients"]:
        print(f"{c['feature']:<32}{c['coefficient']:>+9.3f}{c['odds_ratio']:>12.3f}")
    print()
    e = result["evaluation"]
    print("Held-out evaluation (test split never seen during fitting):")
    print(f"  ROC AUC                 {e['roc_auc']:.3f}   (0.5 = no better than chance)")
    print(f"  Brier score             {e['brier_score']:.3f}   (lower is better)")
    print(f"  Accuracy at 0.5         {e['accuracy_at_0_5']:.3f}")
    print(f"  Majority-class baseline {e['majority_class_accuracy']:.3f}   (always predict the common class)")
    print(f"  Mean predicted rate     {e['mean_predicted_rate']:.1f}%  vs observed {e['observed_test_rate']:.1f}%")
    print()
    print("Reading it: an odds ratio above 1 means higher odds of the outcome for one")
    print("more unit of that predictor (or for that category versus its reference),")
    print("holding the other predictors fixed. Odds ratios are not probability ratios,")
    print("not causal effects, and the two flagged correlated predictors share credit,")
    print("so their individual coefficients are less stable than the rest. A numeric")
    print("predictor whose mean differs across groups takes over part of the raw")
    print("group gap once the model adjusts for it.")


def main() -> None:
    df = make_synthetic_dataset()

    rate_report = outcome_rate_by_group(
        df,
        group_column="group",
        outcome_column="high_income",
        reference_group="Group A",
    )
    _print_rate_report(rate_report)

    regression = fit_logistic_example(
        df,
        outcome_column="high_income",
        numeric_predictors=["age", "education_years", "hours_per_week", "overtime_hours"],
        nominal_predictors={"sector": "Private", "group": "Group A"},
        group_column="group",
    )
    _print_regression_report(regression)


if __name__ == "__main__":
    main()
