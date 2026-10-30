"""User-defined regrouping of categories for a comparison.

A mapping combines chosen categories of a column under a new label. It is
applied to a working copy of the selected columns only; the stored dataset,
the report and earlier comparisons are never changed, and categories are
never combined automatically.

Rules (violations raise ComparisonError, which the API reports as 400):

* A mapping names a selected categorical column and lists combinations, each
  with a ``label`` and the original ``categories`` it combines.
* Labels must be non-empty after trimming and at most ``MAX_LABEL_LENGTH``
  characters. Each combination needs at least one category, and the same
  label may not be used by two combinations.
* Every category must exist in the column. Types matter: the number 1, the
  text "1" and the boolean true are three different categories.
* A category may belong to only one combination.
* Collision: a new label may equal an existing category's name only when that
  category is part of the same combination. Otherwise the label would silently
  merge two groups, so it is rejected.
* Categories that are not mapped keep their original labels, and missing
  values stay missing.
"""

from typing import Optional

import pandas as pd

from backend.diagnostics.comparison_common import ComparisonError, json_label, ordered_counts

MAX_LABEL_LENGTH = 100

REGROUPING_NOTE = (
    "Regrouping changes the question being compared. A different p-value or "
    "fewer warnings do not show that the regrouped comparison is more valid "
    "for your research question. The original dataset and earlier "
    "comparisons are unchanged."
)


def label_key(value) -> tuple:
    """A category's identity: its type and value, so 1, "1" and true differ."""
    value = json_label(value)
    kind = (
        "bool" if isinstance(value, bool)
        else "int" if isinstance(value, int)
        else "float" if isinstance(value, float)
        else "str"
    )
    return (kind, value)


def _describe(value) -> str:
    kind, shown = label_key(value)
    return f"{shown!r} ({kind})"


def _counts(column: pd.Series) -> list:
    return [
        {"label": json_label(label), "count": int(count)}
        for label, count in ordered_counts(column).items()
    ]


def _validated_mapping(name: str, column: pd.Series, combinations: list) -> dict:
    """Return ``{category key: new label}`` after checking every rule."""
    if not isinstance(combinations, list) or not combinations:
        raise ComparisonError(f"Mapping for column '{name}' needs at least one combination.")
    existing = {label_key(value): json_label(value) for value in column.dropna().unique()}
    assigned = {}
    used_labels = {}
    for index, combination in enumerate(combinations, start=1):
        label = str(combination.get("label", "")).strip()
        categories = combination.get("categories") or []
        if not label:
            raise ComparisonError(
                f"Combination {index} for column '{name}' has an empty label."
            )
        if len(label) > MAX_LABEL_LENGTH:
            raise ComparisonError(
                f"The label '{label[:20]}...' for column '{name}' is longer than "
                f"{MAX_LABEL_LENGTH} characters."
            )
        if label in used_labels:
            raise ComparisonError(
                f"The label '{label}' is used by more than one combination for "
                f"column '{name}'. List all categories for one label together."
            )
        used_labels[label] = index
        if not categories:
            raise ComparisonError(
                f"The combination '{label}' for column '{name}' lists no categories."
            )
        own = set()
        for category in categories:
            key = label_key(category)
            if key not in existing:
                raise ComparisonError(
                    f"Category {_describe(category)} does not exist in column '{name}'."
                )
            if key in own:
                raise ComparisonError(
                    f"Category {_describe(category)} is listed twice in '{label}'."
                )
            if key in assigned:
                raise ComparisonError(
                    f"Category {_describe(category)} in column '{name}' is mapped to "
                    f"both '{assigned[key]}' and '{label}'."
                )
            own.add(key)
            assigned[key] = label
        collision = ("str", label)
        if collision in existing and collision not in own:
            raise ComparisonError(
                f"The label '{label}' collides with an existing category of column "
                f"'{name}' that is not part of this combination. Include that "
                "category in the combination or choose another label."
            )
    return assigned


def _apply(column: pd.Series, assigned: dict) -> pd.Series:
    cache = {}

    def convert(value):
        if pd.isna(value):
            return value
        key = label_key(value)
        if key not in cache:
            cache[key] = assigned.get(key, json_label(value))
        return cache[key]

    return column.astype(object).map(convert)


def regroup_columns(df: pd.DataFrame, roles: dict, mappings: Optional[dict], keep: tuple = ()):
    """Apply ``mappings`` to a copy of the columns named in ``roles``.

    ``roles`` maps each selected categorical column to its role ("group" or
    "outcome"); ``keep`` names further columns the comparison needs, copied
    unchanged. Returns ``(working_frame, evidence)``; ``evidence`` is None
    when there is nothing to apply. ``df`` is never modified.
    """
    if not mappings:
        return df, None
    unknown = [name for name in mappings if name not in roles]
    if unknown:
        raise ComparisonError(
            f"Category mappings can only be applied to the selected categorical "
            f"columns ({', '.join(roles)}); '{unknown[0]}' is not one of them."
        )
    working = df[[*roles, *(name for name in keep if name not in roles)]].copy()
    columns = []
    for name, combinations in mappings.items():
        original = working[name]
        assigned = _validated_mapping(name, original, combinations)
        regrouped = _apply(original, assigned)
        before, after = _counts(original), _counts(regrouped)
        working[name] = regrouped
        columns.append(
            {
                "column": name,
                "role": roles[name],
                "mapping": [
                    {
                        "label": str(c["label"]).strip(),
                        "categories": [json_label(x) for x in c["categories"]],
                    }
                    for c in combinations
                ],
                "before": before,
                "after": after,
                "categories_before": len(before),
                "categories_after": len(after),
                "unmapped_categories": len(before) - len(assigned),
                "rows_relabelled": int(sum(c["count"] for c in before if label_key(c["label"]) in assigned)),
                "missing_values": int(original.isna().sum()),
                "missing_values_after": int(regrouped.isna().sum()),
                "count_denominator": "non-missing rows",
            }
        )
    return working, columns


def describe_method_change(before: dict, after: dict) -> dict:
    """Say whether regrouping changed the group count and the applicable method.

    ``before`` and ``after`` hold ``group_count`` and ``method`` (a key plus a
    display ``name``) for the comparison without and with the mapping.
    """
    changed = before["method"]["key"] != after["method"]["key"]
    group_text = (
        f"The number of groups changed from {before['group_count']} to {after['group_count']}."
        if before["group_count"] != after["group_count"]
        else f"The number of groups stayed at {after['group_count']}."
    )
    if changed:
        explanation = (
            f"{group_text} The method changed from {before['method']['name']} "
            f"to {after['method']['name']}. These methods answer different questions, "
            "so the results are not directly comparable."
        )
    else:
        explanation = f"{group_text} The method stays {after['method']['name']}."
    return {
        "group_count_before": before["group_count"],
        "group_count_after": after["group_count"],
        "method_before": before["method"]["key"],
        "method_after": after["method"]["key"],
        "changed": changed,
        "explanation": explanation,
    }
