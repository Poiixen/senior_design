"""Short, deterministic reading layer; full statistical evidence stays available."""


def summarize(candidate):
    v, kind = candidate.values, candidate.finding_type
    columns = candidate.columns
    col = columns[0] if columns else "this dataset"
    summary = "This finding needs a closer look before you use it."
    action = "Review the saved evidence before deciding what to change."
    caution = None
    if kind == "missing_values":
        summary = f"{v['missing_count']} of {v['total_rows']} rows have no {col} value."
        action = "Check why these values are missing before filling them in."
    elif kind == "duplicates":
        summary = f"{v['duplicate_count']} rows repeat an earlier row in the dataset."
        action = "Check whether these are repeated entries or separate events with the same values."
    elif kind == "outliers":
        summary = f"{v['outlier_count']} values in {col} were flagged for review. They are not necessarily mistakes."
        action = "Check a few flagged values against the original records."
        if v.get("q1") is not None and v.get("q1") == v.get("q3"):
            caution = "The middle half of the values is the same, so this rule flags every different value."
        elif v.get("outlier_percentage", 0) >= 20:
            caution = "Many flags can reflect values clustered closely together, rather than errors."
    elif kind in ("group_difference", "categorical_association"):
        group, value = columns
        if v.get("significant_at_0_05"):
            subject = "Averages" if v.get("comparison_basis") == "means" else "Patterns"
            summary = f"{subject} in {value} differ across {group} groups in this test."
        else:
            summary = f"This test did not detect a clear difference in {value} across {group} groups. That does not mean the groups are identical."
        action = "Compare the groups in the chart and decide whether the difference matters for your question."
        caution = "A difference does not tell us what caused it."
        if any("expected" in w.lower() for w in candidate.warnings):
            caution = "Some category counts are too small for a reliable test result. Treat this comparison cautiously."
        elif any("holm" not in w.lower() for w in candidate.warnings):
            caution = "This comparison has data or test limitations. Check Statistical details before relying on it."
        if candidate.exploratory:
            caution += " These comparisons are exploratory; confirm the pattern before making decisions."
    elif kind == "correlation":
        summary = f"{columns[0]} and {columns[1]} tend to vary together in this dataset."
        action = "Review both columns together before deciding how to use them."
        caution = "This does not mean one causes the other."
    elif kind == "skewed_distribution":
        summary = f"{col} has a long tail of {'high' if v['direction'] == 'right' else 'low'} values."
        action = "Check whether the middle value describes a typical record better than the average."
    elif kind in ("small_groups", "unavailable_test"):
        summary = "There is not enough usable information to complete this comparison."
        action = "Check the group sizes and missing values before trying again."
    elif kind == "regrouping":
        summary = f"Categories in {col} were combined for this comparison."
        action = "Check that the new groups still match the question you want to answer."
        caution = "Combining categories changes the question being tested."
    if candidate.visual and candidate.visual.chart_type == "evidence_table":
        action = action.replace("the groups in the chart", "the groups in the saved table")
    return {"plain_summary": summary, "recommended_action": action, "plain_caution": caution}
