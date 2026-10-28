"""Deterministic selection of noteworthy findings from saved results.

Every rule is a pure function of the saved evidence. Rules emit a Candidate
only when the pattern passes its documented threshold, so a clean report
yields no candidates. Scores are produced by ranking.py; see
docs/suggestions-ranking.md for the thresholds below.
"""

from dataclasses import dataclass, field
from math import sqrt
from typing import Optional

from backend.models.suggestions import EvidenceRef
from backend.services.suggestions import visuals
from backend.services.suggestions.evidence import Evidence

MISSING_MIN_PERCENT = 5.0
MISSING_FULL_PERCENT = 30.0
DUPLICATE_FULL_PERCENT = 20.0
OUTLIER_MIN_PERCENT = 1.0
OUTLIER_FULL_PERCENT = 10.0
CORRELATION_MIN = 0.7
SKEW_MIN = 1.0
SKEW_FULL = 3.0
ALPHA = 0.05
SMALL_GROUP = 5
SMALL_DATASET = 30
WARNING_RELIABILITY_FACTOR = 0.75

# Saved reasons that say the test needs more observations.
SMALL_GROUP_REASON_WORDS = ("at least", "fewer than", "too few", "expected count")

# Evidence that only some saved comparisons carry (for example an ANOVA effect
# size or a confidence interval); it is left out rather than reported as null.
OPTIONAL_EVIDENCE = ("mean_difference_ci", "eta_squared")

MULTIPLE_COMPARISON_WARNING = (
    "Several comparisons were examined together and p-values are not adjusted "
    "for that, so treat these results as exploratory."
)


@dataclass
class Candidate:
    finding_type: str
    finding_id: str
    columns: list
    size: float
    coverage: float
    reliability: float
    reason: str
    refs: list
    values: dict
    visual: object
    warnings: list = field(default_factory=list)
    exploratory: bool = False
    # Candidates with the same overlap key describe the same pattern.
    overlap_key: Optional[tuple] = None


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def row_reliability(count: Optional[int]) -> float:
    """Evidence from very few rows is discounted."""
    if count is None:
        return 0.5
    if count < SMALL_GROUP:
        return 0.4
    if count < SMALL_DATASET:
        return 0.7
    return 1.0


def _small_dataset_warning(total_rows: int) -> list:
    if total_rows < SMALL_DATASET:
        return [f"The dataset has only {total_rows} rows, so these patterns may not be stable."]
    return []


def _ref(
    evidence: Evidence,
    result_type: str,
    column: Optional[str] = None,
    comparison_id: Optional[int] = None,
) -> EvidenceRef:
    return EvidenceRef(
        result_type=result_type,
        analysis_id=evidence.analysis_id,
        comparison_id=comparison_id,
        column=column,
    )


def missing_value_findings(evidence: Evidence) -> list:
    total = evidence.total_rows
    candidates = []
    for entry in evidence.report.get("missing_values") or []:
        percent = entry.get("missing_percentage")
        count = entry.get("missing_count")
        column = entry.get("column_name")
        if percent is None or count is None or column is None or percent < MISSING_MIN_PERCENT:
            continue
        ref = _ref(evidence, "missing_values", column)
        candidates.append(
            Candidate(
                finding_type="missing_values",
                finding_id=f"missing_values-{column}",
                columns=[column],
                size=clamp(percent / MISSING_FULL_PERCENT),
                coverage=clamp(percent / 100),
                reliability=row_reliability(total),
                reason=f"{percent:.2f}% of all rows are missing this column.",
                refs=[ref],
                values={
                    "missing_count": count,
                    "present_count": total - count,
                    "total_rows": total,
                    "missing_percentage": percent,
                    "severity": entry.get("severity"),
                },
                visual=visuals.missing_bar(column, ref, count, total),
                warnings=_small_dataset_warning(total),
            )
        )
    return candidates


def duplicate_findings(evidence: Evidence) -> list:
    duplicates = evidence.report.get("duplicates") or {}
    count = duplicates.get("duplicate_count") or 0
    total = evidence.total_rows
    if count <= 0 or total <= 0:
        return []
    percent = duplicates.get("duplicate_percentage")
    if percent is None:
        percent = 100 * count / total
    ref = _ref(evidence, "duplicates")
    return [
        Candidate(
            finding_type="duplicates",
            finding_id="duplicates",
            columns=list(duplicates.get("duplicate_columns") or []),
            size=clamp(percent / DUPLICATE_FULL_PERCENT),
            coverage=clamp(percent / 100),
            reliability=row_reliability(total),
            reason=f"{percent:.2f}% of all rows repeat an earlier row.",
            refs=[ref],
            values={
                "duplicate_count": count,
                "total_rows": total,
                "duplicate_percentage": percent,
                "duplicate_group_count": duplicates.get("duplicate_group_count"),
                "rows_in_duplicate_groups": duplicates.get("rows_in_duplicate_groups"),
                "largest_duplicate_group_size": duplicates.get("largest_duplicate_group_size"),
            },
            visual=visuals.duplicate_bar(ref, count, total),
            warnings=_small_dataset_warning(total),
        )
    ]


def outlier_findings(evidence: Evidence) -> list:
    total = evidence.total_rows
    candidates = []
    for entry in evidence.report.get("outliers") or []:
        percent = entry.get("outlier_percentage")
        column = entry.get("column_name")
        if (
            not column
            or percent is None
            or (entry.get("outlier_count") or 0) <= 0
            or percent < OUTLIER_MIN_PERCENT
        ):
            continue
        ref = _ref(evidence, "outliers", column)
        candidates.append(
            Candidate(
                finding_type="outliers",
                finding_id=f"outliers-{column}",
                columns=[column],
                size=clamp(percent / OUTLIER_FULL_PERCENT),
                coverage=clamp(percent / 100),
                reliability=row_reliability(total),
                reason=f"{percent:.2f}% of values fall outside the IQR bounds.",
                refs=[ref],
                values={
                    key: entry.get(key)
                    for key in (
                        "outlier_count",
                        "outlier_percentage",
                        "q1",
                        "q3",
                        "iqr",
                        "lower_bound",
                        "upper_bound",
                    )
                },
                visual=visuals.outlier_box(column, ref, entry, evidence.profile(column)),
                warnings=_small_dataset_warning(total),
                overlap_key=("distribution", column),
            )
        )
    return candidates


def correlation_findings(evidence: Evidence) -> list:
    correlation = evidence.report.get("correlation") or {}
    columns = correlation.get("columns") or []
    matrix = correlation.get("matrix") or []
    total = evidence.total_rows
    candidates = []
    for i, first in enumerate(columns):
        for j in range(i + 1, len(columns)):
            try:
                value = matrix[i][j]
            except IndexError:
                continue
            if value is None or abs(value) < CORRELATION_MIN:
                continue
            second = columns[j]
            ref = _ref(evidence, "correlation", f"{first}|{second}")
            candidates.append(
                Candidate(
                    finding_type="correlation",
                    finding_id=f"correlation-{first}-{second}",
                    columns=[first, second],
                    size=clamp((abs(value) - 0.5) / 0.5),
                    coverage=1.0,
                    reliability=row_reliability(total),
                    reason=f"The Pearson correlation is {value:.2f}, a strong linear relationship.",
                    refs=[ref],
                    values={"correlation": value, "method": "pearson"},
                    visual=visuals.correlation_pair(ref, first, second, value),
                    warnings=_small_dataset_warning(total),
                )
            )
    return candidates


def skew_findings(evidence: Evidence) -> list:
    """Skewed numeric columns, from the distribution description of Ticket #57.

    Reads ``distribution_shape.skewness`` on numeric column profiles. Reports saved before that result exists produce no findings.
    """
    total = evidence.total_rows
    candidates = []
    for profile in evidence.report.get("column_profiles") or []:
        if profile.get("category") != "numeric":
            continue
        skew = (profile.get("distribution_shape") or {}).get("skewness")
        column = profile.get("name")
        if skew is None or not column or abs(skew) < SKEW_MIN:
            continue
        count = profile.get("non_null_count")
        ref = _ref(evidence, "column_profile", column)
        direction = "right" if skew > 0 else "left"
        tail = "large" if skew > 0 else "small"
        candidates.append(
            Candidate(
                finding_type="skewed_distribution",
                finding_id=f"skewed_distribution-{column}",
                columns=[column],
                size=clamp(abs(skew) / SKEW_FULL),
                coverage=clamp((count or 0) / total) if total else 0.0,
                reliability=row_reliability(count),
                reason=f"The distribution is skewed to the {direction} (long tail of {tail} values); skewness is {skew:.2f}.",
                refs=[ref],
                values={"skewness": skew, "non_null_count": count, "direction": direction},
                visual=visuals.histogram(column, ref, profile.get("histogram"), f"Skewness is {skew:.2f}."),
                warnings=_small_dataset_warning(total),
                overlap_key=("distribution", column),
            )
        )
    return candidates


# --- saved comparisons ------------------------------------------------------


def _method(comparison: dict) -> dict:
    return (comparison.get("test") or {}).get("method") or {}


def _basis(method_key: str) -> str:
    return "ranks" if "kruskal" in method_key or "mann" in method_key else "means"


def _effect_two_groups(groups: list) -> Optional[float]:
    first, second = groups
    n1, n2 = first.get("count") or 0, second.get("count") or 0
    s1, s2 = first.get("std_dev"), second.get("std_dev")
    if n1 < 2 or n2 < 2 or s1 is None or s2 is None:
        return None
    if first.get("mean") is None or second.get("mean") is None:
        return None
    pooled = sqrt(((n1 - 1) * s1**2 + (n2 - 1) * s2**2) / (n1 + n2 - 2))
    if pooled == 0:
        return None
    return abs(first["mean"] - second["mean"]) / pooled


def _effect_many_groups(groups: list, overall_std, basis: str) -> Optional[float]:
    stat = "median" if basis == "ranks" else "mean"
    centers = [group.get(stat) for group in groups]
    if not overall_std or not centers or any(center is None for center in centers):
        return None
    return (max(centers) - min(centers)) / overall_std


def _comparison_columns(comparison: dict) -> list:
    selection = comparison.get("selection") or {}
    return [
        selection.get("group_column"),
        selection.get("value_column") or selection.get("outcome_column"),
    ]


def _comparison_overlap(comparison: dict) -> tuple:
    return ("comparison", comparison.get("comparison_type"), *_comparison_columns(comparison))


def _min_count(sizes: list) -> Optional[int]:
    counts = [size.get("count") for size in sizes if size.get("count") is not None]
    return min(counts) if counts else None


def _unavailable(comparison: dict, evidence: Evidence, reason: Optional[str], sizes: list) -> Candidate:
    comparison_id = comparison["comparison_id"]
    ref = _ref(evidence, "comparison", comparison_id=comparison_id)
    small = any(word in (reason or "").lower() for word in SMALL_GROUP_REASON_WORDS)
    kind = "small_groups" if small else "unavailable_test"
    columns = [column for column in _comparison_columns(comparison) if column]
    rows = comparison.get("rows") or {}
    included, total = rows.get("included") or 0, rows.get("total") or 0
    return Candidate(
        finding_type=kind,
        finding_id=f"{kind}-c{comparison_id}",
        columns=columns,
        size=0.3,
        coverage=clamp(included / total) if total else 0.0,
        reliability=0.4,
        reason="The statistical test could not run, so this comparison supports no conclusion.",
        refs=[ref],
        values={
            "method_name": _method(comparison).get("name"),
            "method_key": _method(comparison).get("key"),
            "status": "unavailable",
            "reason": reason,
            "group_sizes": sizes,
            "comparison_type": comparison.get("comparison_type"),
        },
        visual=visuals.evidence_table(
            f"Group sizes for {' and '.join(columns)}",
            ref,
            [{"label": str(size.get("label")), "value": size.get("count")} for size in sizes],
            "The statistical test did not run, so there is no result to chart.",
            unavailable_fields=["test_result"],
            units="rows",
        ),
        warnings=list(comparison.get("warnings") or []),
        overlap_key=_comparison_overlap(comparison),
    )


def _numeric_comparison(comparison: dict, evidence: Evidence) -> Candidate:
    test = comparison.get("test") or {}
    groups = comparison.get("groups") or []
    sizes = test.get("group_sizes") or [
        {"label": group.get("label"), "count": group.get("count")} for group in groups
    ]
    if comparison.get("status") != "ok" or test.get("status") != "ok":
        reason = comparison.get("reason") if comparison.get("status") != "ok" else test.get("reason")
        return _unavailable(comparison, evidence, reason, sizes)

    comparison_id = comparison["comparison_id"]
    method = _method(comparison)
    basis = _basis(str(method.get("key")))
    overall = comparison.get("overall") or {}
    if len(groups) == 2 and basis == "means":
        effect, measure = _effect_two_groups(groups), "standardized_mean_difference"
    else:
        effect = _effect_many_groups(groups, overall.get("std_dev"), basis)
        measure = f"range_of_group_{'medians' if basis == 'ranks' else 'means'}_over_overall_std_dev"
    p_value = test.get("p_value")
    significant = p_value is not None and p_value < ALPHA
    size = clamp(effect) if effect is not None else 0.0
    if not significant:
        size *= 0.5
    rows = comparison.get("rows") or {}
    total, included = rows.get("total") or 0, rows.get("included") or 0
    minimum = _min_count(sizes)
    warnings = list(comparison.get("warnings") or [])
    if minimum is not None and minimum < SMALL_GROUP:
        warnings.append(f"The smallest group has only {minimum} rows.")
    reliability = row_reliability(minimum) * (
        WARNING_RELIABILITY_FACTOR if comparison.get("warnings") else 1.0
    )
    selection = comparison.get("selection") or {}
    group_column, value_column = selection.get("group_column"), selection.get("value_column")
    ref = _ref(evidence, "comparison", comparison_id=comparison_id)
    effect_text = (
        f"an observed gap of {effect:.2f} standard deviations"
        if effect is not None
        else "no usable effect size"
    )
    return Candidate(
        finding_type="group_difference",
        finding_id=f"group_difference-c{comparison_id}",
        columns=[group_column, value_column],
        size=size,
        coverage=clamp(included / total) if total else 0.0,
        reliability=reliability,
        reason=f"{included} of {total} rows were compared, with {effect_text}.",
        refs=[ref],
        values={
            "method_key": method.get("key"),
            "method_name": method.get("name"),
            "comparison_basis": basis,
            "statistic_name": test.get("statistic_name"),
            "statistic": test.get("statistic"),
            "degrees_of_freedom": test.get("degrees_of_freedom"),
            "p_value": p_value,
            "significant_at_0_05": significant,
            "effect_size": effect,
            "effect_measure": measure,
            "mean_difference": test.get("mean_difference"),
            "mean_difference_ci": test.get("mean_difference_ci"),
            "eta_squared": test.get("eta_squared"),
            "difference_order": test.get("difference_order"),
            "group_sizes": sizes,
            "groups": [
                {key: group.get(key) for key in ("label", "count", "mean", "median")}
                for group in groups
            ],
            "rows_included": included,
            "rows_total": total,
        },
        visual=visuals.group_summary(ref, group_column, value_column, groups, basis=basis),
        warnings=warnings,
        overlap_key=_comparison_overlap(comparison),
    )


def _categorical_comparison(comparison: dict, evidence: Evidence) -> Candidate:
    test = comparison.get("test") or {}
    association = comparison.get("association") or {}
    groups = comparison.get("group_categories") or []
    sizes = [
        {"label": label, "count": count}
        for label, count in zip(groups, comparison.get("group_totals") or [])
    ]
    if comparison.get("status") != "ok" or test.get("status") != "ok":
        reason = comparison.get("reason") if comparison.get("status") != "ok" else test.get("reason")
        return _unavailable(comparison, evidence, reason, sizes)

    comparison_id = comparison["comparison_id"]
    cramers_v = association.get("value") if association.get("status") == "ok" else None
    p_value = test.get("p_value")
    significant = p_value is not None and p_value < ALPHA
    size = clamp(cramers_v / 0.5) if cramers_v is not None else 0.0
    if not significant:
        size *= 0.5
    rows = comparison.get("rows") or {}
    total, included = rows.get("total") or 0, rows.get("included") or 0
    warnings = list(comparison.get("warnings") or [])
    reliability = row_reliability(_min_count(sizes)) * (
        WARNING_RELIABILITY_FACTOR if warnings else 1.0
    )
    selection = comparison.get("selection") or {}
    ref = _ref(evidence, "comparison", comparison_id=comparison_id)
    strength = (
        f"Cramer's V is {cramers_v:.2f}"
        if cramers_v is not None
        else "no association strength was available"
    )
    return Candidate(
        finding_type="categorical_association",
        finding_id=f"categorical_association-c{comparison_id}",
        columns=[selection.get("group_column"), selection.get("outcome_column")],
        size=size,
        coverage=clamp(included / total) if total else 0.0,
        reliability=reliability,
        reason=f"{included} of {total} rows were compared and {strength}.",
        refs=[ref],
        values={
            "method_key": _method(comparison).get("key"),
            "method_name": _method(comparison).get("name"),
            "statistic": test.get("statistic"),
            "degrees_of_freedom": test.get("degrees_of_freedom"),
            "p_value": p_value,
            "significant_at_0_05": significant,
            "cramers_v": cramers_v,
            "group_sizes": sizes,
            "percentage_denominator": comparison.get("percentage_denominator"),
            "rows_included": included,
            "rows_total": total,
        },
        visual=visuals.category_relationship(ref, comparison),
        warnings=warnings,
        overlap_key=_comparison_overlap(comparison),
    )


def _regrouping(comparison: dict, evidence: Evidence) -> list:
    """One finding per regrouped column, from the saved result of Ticket #58.

    Reads ``regrouping.columns[]`` (``column``, ``before``/``after`` lists of
    ``{label, count}``, ``mapping``, ``unmapped_categories``) and
    ``regrouping.method_change``.
    """
    regrouping = comparison.get("regrouping")
    if not isinstance(regrouping, dict):
        return []
    comparison_id = comparison["comparison_id"]
    change = regrouping.get("method_change") or {}
    candidates = []
    for item in regrouping.get("columns") or []:
        column = item.get("column")
        before, after = item.get("before") or [], item.get("after") or []
        ref = _ref(evidence, "comparison", column, comparison_id)
        small = [entry for entry in after if (entry.get("count") or 0) < SMALL_GROUP]
        total = sum(entry.get("count") or 0 for entry in after)
        limitations = []
        if small:
            labels = ", ".join(str(entry.get("label")) for entry in small)
            limitations.append(f"Categories that still have fewer than 5 rows: {labels}.")
        if change.get("changed"):
            limitations.append(change.get("explanation") or "Regrouping changed the statistical method.")
        if before and after:
            visual = visuals.before_after(ref, column, before, after)
        else:
            visual = visuals.evidence_table(
                f"Regrouping of {column}",
                ref,
                [],
                "The saved regrouping has no before and after counts.",
                unavailable_fields=["before", "after"],
            )
        candidates.append(
            Candidate(
                finding_type="regrouping",
                finding_id=f"regrouping-c{comparison_id}-{column}",
                columns=[column] if column else [],
                size=0.3,
                coverage=clamp(sum(entry.get("count") or 0 for entry in small) / total) if total else 0.0,
                reliability=0.9,
                reason="You regrouped categories before comparing, which changes how the result should be read.",
                refs=[ref],
                values={
                    "role": item.get("role"),
                    "categories_before": item.get("categories_before", len(before)),
                    "categories_after": item.get("categories_after", len(after)),
                    "unmapped_categories": item.get("unmapped_categories"),
                    "before": before,
                    "after": after,
                    "mapping": item.get("mapping"),
                    "method_change": change,
                },
                visual=visual,
                warnings=limitations,
                overlap_key=("regrouping", comparison_id, column),
            )
        )
    return candidates


def comparison_findings(evidence: Evidence) -> list:
    candidates = []
    for comparison in evidence.comparisons:
        kind = comparison.get("comparison_type")
        if kind == "categorical_numeric":
            candidate = _numeric_comparison(comparison, evidence)
        elif kind == "categorical_categorical":
            candidate = _categorical_comparison(comparison, evidence)
        else:
            continue
        for key in OPTIONAL_EVIDENCE:
            if candidate.values.get(key) is None:
                candidate.values.pop(key, None)
        candidates.append(candidate)
        candidates.extend(_regrouping(comparison, evidence))
    tested = [
        c for c in candidates if c.finding_type in ("group_difference", "categorical_association")
    ]
    if len(tested) >= 2:
        for candidate in tested:
            candidate.exploratory = True
            candidate.warnings.append(MULTIPLE_COMPARISON_WARNING)
    return candidates


ALL_RULES = (
    missing_value_findings,
    duplicate_findings,
    outlier_findings,
    correlation_findings,
    skew_findings,
    comparison_findings,
)


def collect_candidates(evidence: Evidence) -> list:
    return [candidate for rule in ALL_RULES for candidate in rule(evidence)]
