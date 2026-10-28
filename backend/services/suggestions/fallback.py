"""Deterministic explanations and next steps; used with or without AI.

Wording rules (checked by test_suggestions_text.py):
- warnings come before any interpretation;
- the method that actually ran is named, and mean comparisons are kept
  apart from rank comparisons;
- a non-significant result is never read as proof that groups are alike;
- ANOVA-style tests never name the groups that differ;
- next steps ask for review, never automatic removal;
- no causal, fairness or demographic-bias claims.
"""

from backend.services.suggestions.rules import Candidate

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


def _n(value, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _p(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2e}" if value < 0.001 else f"{value:.3f}"


def _with_warnings(candidate: Candidate, text: str) -> str:
    if not candidate.warnings:
        return text
    return "Warnings: " + " ".join(candidate.warnings) + " " + text


def _missing(c: Candidate) -> dict:
    v, col = c.values, c.columns[0]
    return {
        "title": f"Review missing {col} values",
        "text": (
            f"{col} is missing in {v['missing_percentage']:.2f}% of rows. Missing values "
            "reduce the rows any analysis of this column can use, and what is missing "
            "matters for how results are read."
        ),
        "evidence": [
            f"{v['missing_count']} of {v['total_rows']} rows are missing {col} "
            f"({v['missing_percentage']:.2f}%)."
        ],
        "next_steps": [
            f"Confirm why {col} is missing before choosing how to handle it.",
            "Check whether the missing values concentrate in particular groups.",
        ],
    }


def _duplicates(c: Candidate) -> dict:
    v = c.values
    evidence = [
        f"{v['duplicate_count']} of {v['total_rows']} rows repeat an earlier row "
        f"({v['duplicate_percentage']:.2f}%)."
    ]
    if v.get("duplicate_group_count") is not None:
        evidence.append(
            f"{v['duplicate_group_count']} distinct rows are repeated, covering "
            f"{v.get('rows_in_duplicate_groups')} rows in total."
        )
    return {
        "title": "Review repeated rows",
        "text": (
            f"{v['duplicate_count']} rows repeat an earlier row ({v['duplicate_percentage']:.2f}% "
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
    v, col = c.values, c.columns[0]
    return {
        "title": f"Review outlying values in {col}",
        "text": (
            f"{v['outlier_count']} values in {col} ({v['outlier_percentage']:.2f}%) fall outside "
            f"the IQR bounds of {_n(v['lower_bound'])} to {_n(v['upper_bound'])}. They are "
            "unusual for this column but are not necessarily errors."
        ),
        "evidence": [
            f"{v['outlier_count']} outlying values ({v['outlier_percentage']:.2f}% of values).",
            f"Bounds: {_n(v['lower_bound'])} to {_n(v['upper_bound'])} (Q1 {_n(v['q1'])}, Q3 {_n(v['q3'])}).",
        ],
        "next_steps": [
            "Check the flagged values against the source data.",
            "Decide whether they are valid measurements before choosing how to treat them.",
        ],
    }


def _correlation(c: Candidate) -> dict:
    v = c.values
    first, second = c.columns
    return {
        "title": f"Review the relationship between {first} and {second}",
        "text": (
            f"{first} and {second} have a Pearson correlation of {v['correlation']:.2f}: they "
            "tend to move together in a roughly straight-line pattern. Correlation describes "
            "association only and does not show that either column affects the other."
        ),
        "evidence": [f"Pearson correlation of {first} and {second}: {v['correlation']:.2f}."],
        "next_steps": [
            "Look at how the two columns relate in the data before relying on the number.",
            "If both feed a later analysis, review whether you need both, since closely related columns overlap.",
        ],
    }


def _skew(c: Candidate) -> dict:
    v, col = c.values, c.columns[0]
    tail = "large" if v["direction"] == "right" else "small"
    return {
        "title": f"Review the skewed distribution of {col}",
        "text": (
            f"{col} is skewed to the {v['direction']} (skewness {v['skewness']:.2f}), with a long "
            f"tail of {tail} values. The mean can be pulled toward the tail, so the median may "
            "describe a typical value better."
        ),
        "evidence": [f"Skewness of {col}: {v['skewness']:.2f} across {v['non_null_count']} values."],
        "next_steps": [
            "Review the histogram to see how long the tail is.",
            "Consider whether a rank-based comparison suits this column better than a mean-based one.",
        ],
    }


def _group_difference(c: Candidate) -> dict:
    v = c.values
    group_col, value_col = c.columns
    ranks = v["comparison_basis"] == "ranks"
    name = v.get("method_name") or "The test"
    groups = v["groups"]
    stat = "median" if ranks else "mean"
    if ranks:
        method = (
            f"{name} compares how values of {value_col} rank across the groups defined by {group_col}. It is a "
            "rank comparison, not a comparison of means."
        )
    else:
        method = f"{name} compares the mean of {value_col} across the groups defined by {group_col}."

    if len(groups) == 2 and not ranks:
        first, second = groups
        observed = (
            f"Observed mean {value_col}: {first['label']} {_n(first['mean'])} (n={first['count']}), "
            f"{second['label']} {_n(second['mean'])} (n={second['count']})."
        )
    else:
        centers = [g[stat] for g in groups if g.get(stat) is not None]
        observed = (
            f"Observed group {stat}s of {value_col} range from {_n(min(centers))} to "
            f"{_n(max(centers))} across {len(groups)} groups."
            if centers
            else f"Observed group {stat}s were not available."
        )

    many = len(groups) > 2
    if v["significant_at_0_05"]:
        result = (
            f"The p-value ({_p(v['p_value'])}) is below 0.05, so the data show evidence of a "
            f"difference in {'ranks' if ranks else 'means'} between groups."
        )
        if many:
            result += " The test alone does not say which groups differ from each other."
    else:
        result = (
            f"The p-value ({_p(v['p_value'])}) is not below 0.05, so this comparison did not "
            "detect a difference. That does not show the groups are the same; small or "
            "variable groups can hide real differences."
        )
    text = f"{method} {observed} {result} This describes the groups in this dataset and does not show what causes any difference."

    interval = v.get("mean_difference_ci")
    evidence = [
        f"Method: {name} ({'rank' if ranks else 'mean'} comparison).",
        f"{v['statistic_name'] or 'Statistic'} = {_n(v['statistic'])}, p-value = {_p(v['p_value'])}.",
        "Group sizes: " + ", ".join(f"{s['label']} n={s['count']}" for s in v["group_sizes"]) + ".",
        f"{v['rows_included']} of {v['rows_total']} rows were compared.",
    ]
    if interval and interval.get("lower") is not None and v.get("difference_order"):
        first, second = v["difference_order"]
        evidence.insert(
            2,
            f"Mean difference ({first} minus {second}) = {_n(v['mean_difference'])}, "
            f"{interval['level']:.0%} confidence interval {_n(interval['lower'])} to {_n(interval['upper'])}.",
        )
    if v.get("eta_squared") is not None:
        evidence.insert(2, f"Eta squared = {_n(v['eta_squared'], 3)} (share of variation between groups).")
    steps = ["Use the chart to judge how large the observed differences are in practical terms."]
    if v["significant_at_0_05"] and many:
        steps.append("A pairwise follow-up comparison is needed to see which groups differ.")
    if not v["significant_at_0_05"]:
        steps.append("Check the group sizes before reading anything into the lack of a detected difference.")
    steps.append("Consider whether other columns could account for the pattern before drawing conclusions.")
    if c.exploratory:
        steps.append("Treat results from several comparisons as exploratory and confirm them separately.")
    return {
        "title": f"Compare {value_col} across {group_col} groups",
        "text": text,
        "evidence": evidence,
        "next_steps": steps,
    }


def _categorical(c: Candidate) -> dict:
    v = c.values
    group_col, outcome_col = c.columns
    name = v.get("method_name") or "The test"
    strength = (
        f"Cramer's V is {v['cramers_v']:.2f} (0 means no association, 1 means complete association)."
        if v.get("cramers_v") is not None
        else "No association strength was available."
    )
    if v["significant_at_0_05"]:
        result = (
            f"The p-value ({_p(v['p_value'])}) is below 0.05, so the data show evidence that the "
            f"distribution of {outcome_col} differs across the groups defined by {group_col}."
        )
    else:
        result = (
            f"The p-value ({_p(v['p_value'])}) is not below 0.05, so this comparison did not "
            "detect a difference in the distributions. That does not show the columns are unrelated."
        )
    text = (
        f"{name} checks whether the categories of {outcome_col} are distributed differently across "
        f"{group_col} groups. {strength} {result} This describes association in this dataset and "
        "does not show what causes it."
    )
    steps = [
        "Use the chart to see which categories drive the pattern, reading percentages against the stated denominator.",
        "Consider whether other columns could account for the pattern before drawing conclusions.",
    ]
    if c.exploratory:
        steps.append("Treat results from several comparisons as exploratory and confirm them separately.")
    return {
        "title": f"Compare {outcome_col} across {group_col} groups",
        "text": text,
        "evidence": [
            f"Method: {name}.",
            f"Statistic = {_n(v['statistic'])}, degrees of freedom = {v['degrees_of_freedom']}, p-value = {_p(v['p_value'])}.",
            strength,
            f"{v['rows_included']} of {v['rows_total']} rows were compared.",
        ],
        "next_steps": steps,
    }


def _unavailable(c: Candidate) -> dict:
    v = c.values
    columns = " and ".join(str(col) for col in c.columns)
    name = v.get("method_name") or "The statistical test"
    reason = v.get("reason") or "The saved result gives no reason."
    sizes = ", ".join(f"{s['label']} n={s['count']}" for s in v.get("group_sizes") or [])
    return {
        "title": f"Comparison of {columns} could not be tested",
        "text": (
            f"{name} was not run for {columns}. {reason} No conclusion about a difference can be "
            "drawn from this comparison."
        ),
        "evidence": [f"Reason: {reason}"] + ([f"Group sizes: {sizes}."] if sizes else []),
        "next_steps": [
            "Collect more rows, or regroup sparse categories, then repeat the comparison.",
            "Use the group sizes to see which categories are too small to compare.",
        ],
    }


def _regrouping(c: Candidate) -> dict:
    v = c.values
    col = c.columns[0] if c.columns else "the column"
    change = v.get("method_change") or {}
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
            "Counts after: " + ", ".join(f"{e['label']} n={e['count']}" for e in v.get("after") or []) + ".",
        ],
        "next_steps": [
            "Compare the before and after counts to confirm each group is what you intended.",
            "Review any categories that are still small.",
        ],
    }


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
