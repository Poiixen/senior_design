# Ticket #55 / issue #90: relationship and follow-up demo

Upload [relationship-workflow.csv](examples/relationship-workflow.csv). It has
18 rows, three groups with six observations each, means 10/20/30, and three
extra exact duplicate rows. Duplicate removal would leave 15 rows.

1. Open **Columns**, expand `score`, and inspect its histogram, numerical box
   plot and distribution description. Whiskers use observed values within
   1.5 × IQR; they are not confidence intervals. Older reports show quartiles
   without inventing missing whisker endpoints.
2. In **Relationship explorer**, select `group` and `score`. Choose Welch ANOVA
   to compare means. Inspect the saved group counts, summaries, F statistic,
   both degrees of freedom and small-group warnings. ANOVA does not identify
   which pairs differ. Automatic mode instead uses Kruskal–Wallis for three
   groups, a comparison of ranks.
3. Expand category counts, select B and C, and preview a combined `BC` label.
   Run automatic mode. Reopen the original and regrouped results with **Open
   saved result**. The exact mapping, before/after counts (6/6/6 → 6/12), and
   change to Welch's two-group test remain attached to the saved result.
4. Return to **Overview** and generate **Worth Noting**. Inspect why each card
   was surfaced, its warning, visual and evidence link. The first five cards
   retain backend ranking; **View more findings** reads subsequent pages.
   Change a selection in the explorer or the finding comparison context to
   demonstrate the outdated notice and required regeneration.
5. Ask “Which saved result supports the group difference?” in the report chat.
   When an AI provider is configured, inspect the answer's evidence link. Reload
   the report and reopen its conversation. Without a provider, demonstrate the
   unavailable state and retry; the saved question is not duplicated. Start a
   new conversation or switch reports to show isolation.
6. Select **Preview duplicate removal**. Confirm 18 original, 3 proposed removed,
   and 15 resulting rows. The preview explains exact matching across all columns,
   keeping the first occurrence. There is no apply button. Reopen the report:
   its dataset remains at 18 rows and the original analysis is unchanged.

## Contracts and limits

The frontend uses the existing authenticated comparisons, suggestions,
conversations and questions endpoints. Saved result IDs and evidence fingerprints
remain in finding state. Comparison context changes abort pending generation and
invalidate displayed findings; pagination rejects changed fingerprints.
Requests are aborted on report teardown and report IDs are checked on responses.
Question retries reuse the same request ID, including pending questions restored
from history. Nothing is persisted in browser localStorage.

`POST /api/reports/{analysis_id}/duplicate-preview` is a read-only count operation:

```json
{
  "analysis_id": 1,
  "original_rows": 18,
  "proposed_removed_rows": 3,
  "resulting_rows": 15,
  "definition": "Exact matches across all source columns, including matching missing values. The first occurrence is retained; only extra copies are counted for removal.",
  "note": "Preview only. No changes were applied. The original dataset and saved reports remain unchanged."
}
```

It requires ownership (404 for missing/other-user reports), returns 409 when
source rows were not retained, and never saves or applies cleaning changes.
New numeric profiles add `count`, `whisker_low`, `whisker_high`, and
`outlier_count`; all existing fields remain intact.

Pairwise post-hoc tests, cleaned exports and applying cleaning changes remain
out of scope. No scatter points or per-group confidence intervals are invented.
Saved correlations do not include pair sample sizes. Category pickers show the
backend's omission counts when its 500-category limit is reached. Follow-up
answers depend on a configured AI provider; deterministic ranked suggestions
remain available without one. Future work can add pair sample sizes and raw
outlier points to the backend chart contract.

## Regression checks

Run `npm.cmd run typecheck`, `npm.cmd test` and `npm.cmd run test:e2e` from
`frontend`, and `python -m pytest -q` from the repository root. Browser tests use
real committed numerical/regrouping responses, controlled AI replies, desktop
and mobile layouts, pagination, stale context, and delayed responses after
report navigation. Backend tests replay both shared demo packs and verify
authorization, conversation isolation, retry idempotency and byte-for-byte
source preservation after previews. Existing upload, report, session and
categorical comparison regressions remain in those suites.
