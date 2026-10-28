"""Chart specifications built only from saved aggregate results.

Each builder copies numbers out of a saved result. When a field the chart
needs is absent the builder returns an ``evidence_table`` with the reason
instead of inventing values.
"""

from typing import Optional

from backend.models.suggestions import EvidenceRef, VisualSpec

BOX_FIELDS = ("min", "q1", "median", "q3", "max")
WHISKER_FIELDS = ("whisker_low", "whisker_high", "outlier_count")
WHISKER_NOTE = (
    "Whiskers reach the most extreme values within 1.5 x IQR of the quartiles; "
    "they are not confidence intervals."
)
MAX_PERCENTAGE_BAR_CELLS = 36


def evidence_table(
    title: str,
    source: EvidenceRef,
    rows: list,
    reason: str,
    *,
    unavailable_fields: Optional[list] = None,
    units: Optional[str] = None,
    warnings: Optional[list] = None,
) -> VisualSpec:
    return VisualSpec(
        chart_type="evidence_table",
        title=title,
        source=source,
        data={"rows": rows},
        units=units,
        warnings=warnings or [],
        unavailable_fields=unavailable_fields or [],
        fallback_reason=reason,
    )


def missing_bar(column: str, source: EvidenceRef, missing: int, total: int) -> VisualSpec:
    return VisualSpec(
        chart_type="bar",
        title=f"Missing and present values in {column}",
        source=source,
        data={"categories": ["Missing", "Present"], "values": [missing, total - missing]},
        x_label="Value status",
        y_label="Rows",
        units="rows",
        percent_denominator="all rows in the report",
    )


def duplicate_bar(source: EvidenceRef, repeated: int, total: int) -> VisualSpec:
    return VisualSpec(
        chart_type="bar",
        title="Repeated rows and other rows",
        source=source,
        data={
            "categories": ["Repeated rows (extra copies)", "Other rows"],
            "values": [repeated, total - repeated],
        },
        x_label="Row type",
        y_label="Rows",
        units="rows",
        percent_denominator="all rows in the report",
    )


def outlier_box(column: str, source: EvidenceRef, outlier: dict, profile: Optional[dict]) -> VisualSpec:
    data = {
        key: outlier.get(key)
        for key in ("q1", "q3", "iqr", "lower_bound", "upper_bound", "outlier_count")
    }
    missing_fields = []
    for key in ("min", "median", "max"):
        value = (profile or {}).get(key)
        data[key] = value
        if value is None:
            missing_fields.append(key)
    if data["q1"] is None or data["q3"] is None:
        return evidence_table(
            f"Outlier bounds for {column}",
            source,
            [{"label": key, "value": outlier.get(key)} for key in ("outlier_count", "lower_bound", "upper_bound")],
            "The saved outlier result has no quartiles to draw.",
            unavailable_fields=["q1", "q3"],
        )
    return VisualSpec(
        chart_type="box_plot",
        title=f"Distribution of {column} with outlier bounds",
        source=source,
        data=data,
        x_label=None,
        y_label=column,
        percent_denominator="non-missing values",
        warnings=["Outlier bounds are Q1 - 1.5*IQR and Q3 + 1.5*IQR."],
        unavailable_fields=missing_fields,
    )


def histogram(column: str, source: EvidenceRef, histogram_data: Optional[dict], note: Optional[str] = None) -> VisualSpec:
    counts = (histogram_data or {}).get("counts") or []
    edges = (histogram_data or {}).get("bin_edges") or []
    if not counts or len(edges) != len(counts) + 1:
        return evidence_table(
            f"Distribution of {column}",
            source,
            [],
            "The saved profile has no histogram for this column.",
            unavailable_fields=["histogram"],
        )
    return VisualSpec(
        chart_type="histogram",
        title=f"Distribution of {column}",
        source=source,
        data={"bin_edges": edges, "counts": counts},
        x_label=column,
        y_label="Rows",
        units="rows",
        warnings=[note] if note else [],
    )


def correlation_pair(source: EvidenceRef, first: str, second: str, value: float) -> VisualSpec:
    return VisualSpec(
        chart_type="correlation_pair",
        title=f"Correlation of {first} and {second}",
        source=source,
        data={"columns": [first, second], "value": value},
        x_label=first,
        y_label=second,
        warnings=["Saved results hold the correlation value, not the row-level points."],
        unavailable_fields=["scatter_points"],
    )


def group_summary(source: EvidenceRef, group_column: str, value_column: str, groups: list, *, basis: str) -> VisualSpec:
    """Grouped box plot when every group has quartiles, else a mean bar chart."""
    title = f"{value_column} by {group_column}"
    if groups and all(all(group.get(key) is not None for key in BOX_FIELDS) for group in groups):
        has_whiskers = all(group.get(key) is not None for group in groups for key in WHISKER_FIELDS)
        return VisualSpec(
            chart_type="grouped_box",
            title=title,
            source=source,
            data={
                "groups": [
                    {key: group.get(key) for key in ("label", "count", "mean", *BOX_FIELDS, *WHISKER_FIELDS)}
                    for group in groups
                ]
            },
            x_label=group_column,
            y_label=value_column,
            warnings=[WHISKER_NOTE] if has_whiskers else [],
            unavailable_fields=[] if has_whiskers else list(WHISKER_FIELDS),
        )
    if groups and all(group.get("mean") is not None for group in groups):
        return VisualSpec(
            chart_type="bar",
            title=f"Mean of {value_column} by {group_column}",
            source=source,
            data={"categories": [str(g["label"]) for g in groups], "values": [g["mean"] for g in groups]},
            x_label=group_column,
            y_label=f"Mean of {value_column}",
            unavailable_fields=list(BOX_FIELDS),
        )
    return evidence_table(
        title,
        source,
        [],
        "The saved comparison has no group summaries to chart.",
        unavailable_fields=["groups"],
    )


def category_relationship(source: EvidenceRef, comparison: dict) -> VisualSpec:
    group_column = comparison["selection"]["group_column"]
    outcome_column = comparison["selection"]["outcome_column"]
    groups = comparison.get("group_categories") or []
    outcomes = comparison.get("outcome_categories") or []
    counts = comparison.get("counts")
    percentages = comparison.get("row_percentages")
    denominator = comparison.get("percentage_denominator")
    if not (groups and outcomes and counts and percentages):
        return evidence_table(
            f"{outcome_column} by {group_column}",
            source,
            [],
            "The saved comparison has no contingency table to chart.",
            unavailable_fields=["counts", "row_percentages"],
        )
    if len(groups) * len(outcomes) <= MAX_PERCENTAGE_BAR_CELLS:
        return VisualSpec(
            chart_type="grouped_percentage_bar",
            title=f"{outcome_column} by {group_column}",
            source=source,
            data={"group_categories": groups, "outcome_categories": outcomes, "row_percentages": percentages, "counts": counts},
            x_label=group_column,
            y_label=f"Percent of each {group_column} group",
            units="percent",
            percent_denominator=denominator,
        )
    return VisualSpec(
        chart_type="contingency_heatmap",
        title=f"{outcome_column} by {group_column}",
        source=source,
        data={"group_categories": groups, "outcome_categories": outcomes, "counts": counts},
        x_label=outcome_column,
        y_label=group_column,
        units="rows",
    )


def before_after(source: EvidenceRef, column: str, before: list, after: list) -> VisualSpec:
    return VisualSpec(
        chart_type="before_after_bar",
        title=f"Category counts of {column} before and after regrouping",
        source=source,
        data={"before": before, "after": after},
        x_label=column,
        y_label="Rows",
        units="rows",
    )
