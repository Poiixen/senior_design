"""Deterministic explanations and next steps; used with or without AI.

Every finding becomes four parts: ``title``, ``explanation``, ``evidence``
and ``next_steps``. Nothing here computes statistics; it only words the
values that rules.py already saved on the Candidate.

Wording rules (checked by test_suggestions_rules.py):
- warnings come before any interpretation;
- the method that actually ran is named, and mean comparisons are kept
  apart from rank comparisons;
- a non-significant result is never read as proof that groups are alike;
- ANOVA-style tests never name the groups that differ;
- next steps ask for review, never automatic removal;
- no causal, fairness or demographic-bias claims;
- effect-size labels describe magnitude in this dataset only, never
  importance or cause.
"""

from math import sqrt

from backend.services.suggestions.rules import Candidate


# =============================================================================
# Wording guards
# =============================================================================

# Lower-case phrases no explanation or next step may contain.
BANNED_PHRASES = (
    "no difference",
    "proves",
    "proven",
    "caused by",
    "because of",
    "delete",
    "remove",
    "drop the",
    "drop this",
    "biased",
    "unfair",
    "discriminat",
    "are equal",
    "is equal",
)

SIZE_CAVEAT = "The size label describes magnitude in this dataset, not practical importance or cause."

# Next steps shared by every tested comparison.
OTHER_COLUMNS_STEP = "Consider whether other columns could account for the pattern before drawing conclusions."
EXPLORATORY_STEP = "Treat results from several comparisons as exploratory and confirm them separately."


# =============================================================================
# Number formatting
# =============================================================================


def _n(value, digits: int = 2) -> str:
    """A number rounded for display, e.g. 34.1757 -> "34.18"."""
    return "n/a" if value is None else f"{value:.{digits}f}"


def _p(value) -> str:
    """A p-value, in scientific notation when below 0.001."""
    if value is None:
        return "n/a"
    return f"{value:.2e}" if value < 0.001 else f"{value:.3f}"


def _df(value) -> str:
    """Degrees of freedom: whole numbers stay whole, Welch's df keeps 2 decimals."""
    if value is None:
        return "n/a"
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}"


# =============================================================================
# Effect-size labels (Cohen, 1988)
# =============================================================================
#
# A p-value only says whether a difference is detectable; with enough rows even
# a tiny gap is "significant". An effect size says how big the gap is, on a
# scale that does not grow with sample size. Cohen's conventional cut-offs:
#
#   Cohen's d     Gap between two group means, in pooled standard deviations.
#                 d = |mean1 - mean2| / pooled SD. d = 1 means the means sit
#                 one typical spread apart.
#   Eta squared   Share of the total variation that lies between groups rather
#                 than within them (0 to 1). Reported by ANOVA.
#   Cohen's w     Strength of association in a contingency table. Cramer's V
#                 rescales it to 0..1, so V's cut-offs depend on table size.
#
# The labels are conventions for magnitude only. They do not say whether a gap
# matters in practice, and never say what produced it.

#                  small  medium  large
COHENS_D_CUTS    = (0.2,  0.5,    0.8)
ETA_SQUARED_CUTS = (0.01, 0.06,   0.14)
COHENS_W_CUTS    = (0.1,  0.3,    0.5)  # scaled per table size for Cramer's V


def _size_label(value, cuts, words=("small", "medium", "large")) -> str:
    """Place ``value`` against three cut-offs; below the first is "negligible"."""
    value = abs(value)
    if value < cuts[0]:
        return "negligible"
    if value < cuts[1]:
        return words[0]
    if value < cuts[2]:
        return words[1]
    return words[2]


def _cramers_v_cuts(v: dict):
    """Cramer's V cut-offs for this table, or None when its shape is unknown.

    Cohen's w cut-offs are divided by sqrt(min(rows, columns) - 1). The
    shape is recovered from the group count and df = (rows - 1)(columns - 1).
    """
    groups = len(v.get("group_sizes") or [])
    dof = v.get("degrees_of_freedom")
    if groups < 2 or not dof:
        return None

    smaller = min(groups - 1, dof / (groups - 1))
    if smaller < 1:
        return None
    return tuple(cut / sqrt(smaller) for cut in COHENS_W_CUTS)


# =============================================================================
# Shared pieces
# =============================================================================


def _with_warnings(candidate: Candidate, text: str) -> str:
    """Put any warnings in front of the explanation."""
    if not candidate.warnings:
        return text
    return "Warnings: " + " ".join(candidate.warnings) + " " + text


def _sizes_line(sizes: list) -> str:
    """ "Group sizes: a n=3, b n=5." """
    return "Group sizes: " + ", ".join(f"{s['label']} n={s['count']}" for s in sizes) + "."


def _rows_line(v: dict) -> str:
    return f"{v['rows_included']} of {v['rows_total']} rows were compared."


# =============================================================================
# Data-quality findings
# =============================================================================


def _missing(c: Candidate) -> dict:
    """Share of rows with no value in a column."""
    v, col = c.values, c.columns[0]
    percent = f"{v['missing_percentage']:.2f}%"

    return {
        "title": f"Review missing {col} values",
        "text": (
            f"{col} is missing in {percent} of rows. Missing values "
            "reduce the rows any analysis of this column can use, and what is missing "
            "matters for how results are read."
        ),
        "evidence": [
            f"{v['missing_count']} of {v['total_rows']} rows are missing {col} ({percent}).",
        ],
        "next_steps": [
            f"Confirm why {col} is missing before choosing how to handle it.",
            "Check whether the missing values concentrate in particular groups.",
        ],
    }


def _duplicates(c: Candidate) -> dict:
    """Rows that repeat an earlier row under the report's duplicate definition."""
    v = c.values
    percent = f"{v['duplicate_percentage']:.2f}%"

    evidence = [f"{v['duplicate_count']} of {v['total_rows']} rows repeat an earlier row ({percent})."]
    if v.get("duplicate_group_count") is not None:
        evidence.append(
            f"{v['duplicate_group_count']} distinct rows are repeated, covering "
            f"{v.get('rows_in_duplicate_groups')} rows in total."
        )

    return {
        "title": "Review repeated rows",
        "text": (
            f"{v['duplicate_count']} rows repeat an earlier row ({percent} "
            "of rows), using the report's duplicate definition. Repeated rows can give "
            "those records extra weight in later comparisons."
        ),
        "evidence": evidence,
        "next_steps": [
            "Inspect the repeated rows to see whether they are true copies or separate records that happen to match.",
            "Decide with the data owner whether they belong in the analysis.",
        ],
    }


def _outliers(c: Candidate) -> dict:
    """Values outside the IQR fences (Tukey's rule).

    IQR = Q3 - Q1, the spread of the middle half of the data. Values below
    Q1 - 1.5 * IQR or above Q3 + 1.5 * IQR are flagged. The rule does not
    assume a normal distribution, but flagged values are only unusual, not wrong.
    """
    v, col = c.values, c.columns[0]
    count = f"{v['outlier_count']}"
    percent = f"{v['outlier_percentage']:.2f}%"
    bounds = f"{_n(v['lower_bound'])} to {_n(v['upper_bound'])}"

    return {
        "title": f"Review outlying values in {col}",
        "text": (
            f"{count} values in {col} ({percent}) fall outside the IQR bounds of {bounds}. "
            "They are unusual for this column but are not necessarily errors."
        ),
        "evidence": [
            f"{count} outlying values ({percent} of values).",
            f"Bounds: {bounds} (Q1 {_n(v['q1'])}, Q3 {_n(v['q3'])}).",
        ],
        "next_steps": [
            "Check the flagged values against the source data.",
            "Decide whether they are valid measurements before choosing how to treat them.",
        ],
    }


def _correlation(c: Candidate) -> dict:
    """Pearson correlation (r) between two numeric columns.

    r runs from -1 to 1 and measures how closely the points follow a straight
    line: near 1, both rise together; near -1, one falls as the other rises;
    near 0, no straight-line pattern (a curved one may still exist). It is
    sensitive to outliers and describes association only.
    """
    first, second = c.columns
    r = f"{c.values['correlation']:.2f}"

    return {
        "title": f"Review the relationship between {first} and {second}",
        "text": (
            f"{first} and {second} have a Pearson correlation of {r}: they "
            "tend to move together in a roughly straight-line pattern. Correlation describes "
            "association only and does not show that either column affects the other."
        ),
        "evidence": [f"Pearson correlation of {first} and {second}: {r}."],
        "next_steps": [
            "Look at how the two columns relate in the data before relying on the number.",
            "If both feed a later analysis, review whether you need both, since closely related columns overlap.",
        ],
    }


def _skew(c: Candidate) -> dict:
    """Skewness: how lopsided a distribution is.

    0 is symmetric. Positive (right skew) means a long tail of large values,
    as with incomes; negative (left skew) a long tail of small values. Beyond
    about +/-1 the mean is pulled toward the tail, so the median is often the
    better summary and rank-based tests are often the safer choice.
    """
    v, col = c.values, c.columns[0]
    skewness = f"{v['skewness']:.2f}"
    tail = "large" if v["direction"] == "right" else "small"

    return {
        "title": f"Review the skewed distribution of {col}",
        "text": (
            f"{col} is skewed to the {v['direction']} (skewness {skewness}), with a long "
            f"tail of {tail} values. The mean can be pulled toward the tail, so the median may "
            "describe a typical value better."
        ),
        "evidence": [f"Skewness of {col}: {skewness} across {v['non_null_count']} values."],
        "next_steps": [
            "Review the histogram to see how long the tail is.",
            "Consider whether a rank-based comparison suits this column better than a mean-based one.",
        ],
    }


# =============================================================================
# Numeric value compared across groups (Welch's t-test, Kruskal-Wallis, ANOVA)
# =============================================================================
#
# The analysis picks the test; this code only words its result. Today it runs
# Welch's t-test for two groups and Kruskal-Wallis for three or more; the
# wording also covers Mann-Whitney U and ANOVA if those are added.
#
#   Welch's t-test       Two groups. Asks whether the two means differ, without
#                        assuming equal variances, which is why its degrees of
#                        freedom are usually fractional (e.g. 112.08). Statistic t
#                        is the mean gap divided by its standard error.
#
#   Mann-Whitney U       Two groups, rank-based. Asks whether values in one group
#                        tend to be larger than in the other. Uses ranks, so it
#                        is robust to skew and outliers. Not a test of means.
#
#   One-way ANOVA        Three or more groups. Asks whether at least one group
#                        mean differs, by comparing variation between groups with
#                        variation within them (statistic F). It does not say
#                        which groups differ; that needs a pairwise follow-up.
#
#   Kruskal-Wallis H     Rank-based counterpart of ANOVA for three or more groups.
#                        Asks whether some groups tend to have higher values. Not
#                        a test of means, and it does not say which groups differ.
#
# Every test gives a p-value: the chance of a gap at least this large if the
# groups truly did not differ. Below 0.05 counts as evidence of a difference.
# Above 0.05 only means none was detected; small or noisy groups can hide one.


def _group_method(name: str, value_col: str, group_col: str, ranks: bool) -> str:
    """Which test ran, keeping rank comparisons apart from mean comparisons."""
    if ranks:
        return (
            f"{name} compares how values of {value_col} rank across the groups defined by {group_col}. "
            "It is a rank comparison, not a comparison of means."
        )
    return f"{name} compares the mean of {value_col} across the groups defined by {group_col}."


def _group_observed(groups: list, value_col: str, stat: str) -> str:
    """Observed centres. Three or more groups get only a range, so no group is named."""
    if len(groups) == 2:
        other = "median" if stat == "mean" else "mean"
        parts = [
            f"{g['label']} {_n(g.get(stat))} ({other} {_n(g.get(other))}, n={g['count']})"
            for g in groups
        ]
        return f"Observed {stat} {value_col}: " + ", ".join(parts) + "."

    centers = [g[stat] for g in groups if g.get(stat) is not None]
    if not centers:
        return f"Observed group {stat}s were not available."
    return (
        f"Observed group {stat}s of {value_col} range from {_n(min(centers))} to "
        f"{_n(max(centers))} across {len(groups)} groups."
    )


def _group_result(v: dict, ranks: bool, many: bool) -> str:
    """Test statistic with df, then what the p-value does and does not show."""
    statistic = f"{v['statistic_name'] or 'Statistic'} = {_n(v['statistic'])}"
    if v.get("degrees_of_freedom") is not None:
        statistic += f" with {_df(v['degrees_of_freedom'])} degrees of freedom"

    p = _p(v["p_value"])
    if v["significant_at_0_05"]:
        reading = (
            f"The p-value ({p}) is below 0.05, so the data show evidence of a "
            f"difference in {'ranks' if ranks else 'means'} between groups."
        )
        if many:
            reading += " The test alone does not say which groups differ from each other."
    else:
        reading = (
            f"The p-value ({p}) is not below 0.05, so this comparison did not "
            "detect a difference. That does not show the groups are the same; small or "
            "variable groups can hide real differences."
        )

    return f"The test gave {statistic}. {reading}"


def _group_effect(v: dict, value_col: str, stat: str):
    """Effect-size sentences, evidence lines and whether a size label was used."""
    sentences, evidence, labelled = [], [], False
    effect, measure = v.get("effect_size"), v.get("effect_measure")

    # Two groups, mean test: Cohen's d.
    if effect is not None and measure == "standardized_mean_difference":
        label = _size_label(effect, COHENS_D_CUTS)
        sentences.append(
            f"The group means are {_n(effect)} pooled standard deviations apart (Cohen's d), "
            f"a {label} gap by Cohen's benchmarks."
        )
        evidence.append(f"Effect size: Cohen's d = {_n(effect)} ({label}).")
        labelled = True

    # Rank test or 3+ groups: spread of group centres. No benchmark exists, so no label.
    elif effect is not None:
        sentences.append(
            f"The highest and lowest group {stat}s are {_n(effect)} overall standard deviations apart."
        )
        evidence.append(f"Effect size: range of group {stat}s = {_n(effect)} overall standard deviations.")

    # ANOVA: eta squared.
    if v.get("eta_squared") is not None:
        eta = v["eta_squared"]
        label = _size_label(eta, ETA_SQUARED_CUTS)
        sentences.append(
            f"Eta squared is {_n(eta, 3)}: about {eta:.0%} of the variation in {value_col} lies between "
            f"groups rather than within them, a {label} effect by Cohen's benchmarks."
        )
        evidence.append(f"Eta squared = {_n(eta, 3)} (share of variation between groups; {label}).")
        labelled = True

    return sentences, evidence, labelled


def _mean_difference_ci(v: dict):
    """``(first, second, interval)`` when a confidence interval was saved, else None."""
    interval = v.get("mean_difference_ci")
    if interval and interval.get("lower") is not None and v.get("difference_order"):
        first, second = v["difference_order"]
        return first, second, interval
    return None


def _group_summaries(v: dict, groups: list) -> str:
    """Mean, median and n per group; group sizes only when no centres were saved."""
    if not any(g.get("mean") is not None or g.get("median") is not None for g in groups):
        return _sizes_line(v["group_sizes"])
    parts = [
        f"{g['label']} mean {_n(g.get('mean'))}, median {_n(g.get('median'))}, n={g['count']}"
        for g in groups
    ]
    return "Group summaries: " + "; ".join(parts) + "."


def _group_steps(c: Candidate, many: bool) -> list:
    significant = c.values["significant_at_0_05"]

    steps = ["Use the chart to judge how large the observed differences are in practical terms."]
    if significant and many:
        steps.append("A pairwise follow-up comparison is needed to see which groups differ.")
    if not significant:
        steps.append("Check the group sizes before reading anything into the lack of a detected difference.")
    steps.append(OTHER_COLUMNS_STEP)
    if c.exploratory:
        steps.append(EXPLORATORY_STEP)
    return steps


def _group_difference(c: Candidate) -> dict:
    v = c.values
    group_col, value_col = c.columns
    groups = v["groups"]
    name = v.get("method_name") or "The test"
    ranks = v["comparison_basis"] == "ranks"
    stat = "median" if ranks else "mean"
    many = len(groups) > 2

    # --- Explanation -------------------------------------------------------
    size, size_evidence, labelled = _group_effect(v, value_col, stat)

    ci = _mean_difference_ci(v)
    if ci:
        first, second, interval = ci
        size.append(
            f"The {interval['level']:.0%} confidence interval for the mean difference ({first} minus "
            f"{second}) runs from {_n(interval['lower'])} to {_n(interval['upper'])}."
        )
    if labelled:
        size.append(SIZE_CAVEAT)

    text = " ".join([
        _group_method(name, value_col, group_col, ranks),
        _group_observed(groups, value_col, stat),
        _group_result(v, ranks, many),
        *size,
        "This describes the groups in this dataset and does not show what causes any difference.",
    ])

    # --- Evidence ----------------------------------------------------------
    evidence = [
        f"Method: {name} ({'rank' if ranks else 'mean'} comparison).",
        f"{v['statistic_name'] or 'Statistic'} = {_n(v['statistic'])}, "
        f"degrees of freedom = {_df(v.get('degrees_of_freedom'))}, p-value = {_p(v['p_value'])}.",
    ]
    if ci:
        evidence.append(
            f"Mean difference ({first} minus {second}) = {_n(v['mean_difference'])}, "
            f"{interval['level']:.0%} confidence interval {_n(interval['lower'])} to {_n(interval['upper'])}."
        )
    evidence += [
        *size_evidence,
        _group_summaries(v, groups),
        _rows_line(v),
    ]

    return {
        "title": f"Compare {value_col} across {group_col} groups",
        "text": text,
        "evidence": evidence,
        "next_steps": _group_steps(c, many),
    }


# =============================================================================
# Category compared across groups (chi-square test + Cramer's V)
# =============================================================================
#
#   Pearson's chi-square  Builds a table of counts (groups x outcome categories)
#   test of independence  and compares it with the counts expected if the two
#                         columns were unrelated. Big gaps give a large
#                         chi-square statistic and a small p-value. Degrees of
#                         freedom = (rows - 1) x (columns - 1). The p-value is
#                         unreliable when expected counts are small (under 5).
#
#   Cramer's V            How strong the association is, from 0 (none) to 1
#                         (one column fully determines the other). Unlike the
#                         p-value it does not grow with sample size, and it says
#                         nothing about direction or cause.


def _categorical(c: Candidate) -> dict:
    v = c.values
    group_col, outcome_col = c.columns
    name = v.get("method_name") or "The test"
    p = _p(v["p_value"])
    dof = _df(v["degrees_of_freedom"])
    statistic_name = "Chi-square" if "chi_square" in str(v.get("method_key")) else "Statistic"

    # --- Strength of association ------------------------------------------
    cramers_v, cuts = v.get("cramers_v"), _cramers_v_cuts(v)
    label = None
    if cramers_v is not None and cuts:
        label = _size_label(cramers_v, cuts, ("weak", "moderate", "strong"))

    scale = "(0 means no association, 1 means complete association)."
    if cramers_v is None:
        strength = "No association strength was available."
        strength_evidence = strength
    elif label:
        strength = (
            f"Cramer's V is {cramers_v:.2f}, a {label} association by Cohen's benchmarks "
            f"for a table of this size {scale}"
        )
        strength_evidence = f"Cramer's V = {_n(cramers_v)} ({label})."
    else:
        strength = f"Cramer's V is {cramers_v:.2f} {scale}"
        strength_evidence = f"Cramer's V = {_n(cramers_v)}."

    # --- What the p-value shows -------------------------------------------
    if v["significant_at_0_05"]:
        result = (
            f"The p-value ({p}) is below 0.05, so the data show evidence that the "
            f"distribution of {outcome_col} differs across the groups defined by {group_col}."
        )
    else:
        result = (
            f"The p-value ({p}) is not below 0.05, so this comparison did not "
            "detect a difference in the distributions. That does not show the columns are unrelated."
        )

    # --- Explanation -------------------------------------------------------
    text = " ".join([
        f"{name} checks whether the categories of {outcome_col} are distributed differently "
        f"across {group_col} groups.",
        f"The test gave {statistic_name.lower()} = {_n(v['statistic'])} with {dof} degrees of freedom.",
        result,
        strength,
        *([SIZE_CAVEAT] if label else []),
        "This describes association in this dataset and does not show what causes it.",
    ])

    # --- Evidence and next steps ------------------------------------------
    sizes = v.get("group_sizes") or []
    evidence = [
        f"Method: {name}.",
        f"{statistic_name} = {_n(v['statistic'])}, degrees of freedom = {dof}, p-value = {p}.",
        strength_evidence,
        *([_sizes_line(sizes)] if sizes else []),
        _rows_line(v),
    ]

    steps = [
        "Use the chart to see which categories drive the pattern, reading percentages against the stated denominator.",
        OTHER_COLUMNS_STEP,
    ]
    if c.exploratory:
        steps.append(EXPLORATORY_STEP)

    return {
        "title": f"Compare {outcome_col} across {group_col} groups",
        "text": text,
        "evidence": evidence,
        "next_steps": steps,
    }


# =============================================================================
# Comparisons that could not run, and regrouped categories
# =============================================================================


def _unavailable(c: Candidate) -> dict:
    """A test that did not run, usually because groups were too small or only
    one category was present. No result exists, so nothing is concluded."""
    v = c.values
    columns = " and ".join(str(col) for col in c.columns)
    name = v.get("method_name") or "The statistical test"
    reason = v.get("reason") or "The saved result gives no reason."
    sizes = v.get("group_sizes") or []

    return {
        "title": f"Comparison of {columns} could not be tested",
        "text": (
            f"{name} was not run for {columns}. {reason} "
            "No conclusion about a difference can be drawn from this comparison."
        ),
        "evidence": [f"Reason: {reason}", *([_sizes_line(sizes)] if sizes else [])],
        "next_steps": [
            "Collect more rows, or regroup sparse categories, then repeat the comparison.",
            "Use the group sizes to see which categories are too small to compare.",
        ],
    }


def _regrouping(c: Candidate) -> dict:
    """Categories the user merged before comparing. The test then answers a
    question about the new groups, which can also change which test runs."""
    v = c.values
    col = c.columns[0] if c.columns else "the column"
    change = v.get("method_change") or {}
    after = ", ".join(f"{e['label']} n={e['count']}" for e in v.get("after") or [])

    text = (
        f"You combined {v['categories_before']} categories of {col} into {v['categories_after']}. "
        "The comparison uses the regrouped categories, so it answers a different question from one on the "
        "original categories, and a different p-value or fewer warnings do not show that it is more "
        "valid for your research question."
    )
    if change.get("changed"):
        text += " " + change["explanation"]

    return {
        "title": f"Review the regrouped categories of {col}",
        "text": text,
        "evidence": [
            f"Categories before regrouping: {v['categories_before']}; after: {v['categories_after']}.",
            f"Counts after: {after}.",
        ],
        "next_steps": [
            "Compare the before and after counts to confirm each group is what you intended.",
            "Review any categories that are still small.",
        ],
    }


# =============================================================================
# Entry point
# =============================================================================

BUILDERS = {
    "missing_values": _missing,
    "duplicates": _duplicates,
    "outliers": _outliers,
    "correlation": _correlation,
    "skewed_distribution": _skew,
    "group_difference": _group_difference,
    "categorical_association": _categorical,
    "unavailable_test": _unavailable,
    "small_groups": _unavailable,
    "regrouping": _regrouping,
}


def describe(candidate: Candidate) -> dict:
    """Return ``title``, ``explanation``, ``evidence`` and ``next_steps``."""
    parts = BUILDERS[candidate.finding_type](candidate)
    return {
        "title": parts["title"],
        "explanation": _with_warnings(candidate, parts["text"]),
        "evidence": parts["evidence"],
        "next_steps": parts["next_steps"],
    }
