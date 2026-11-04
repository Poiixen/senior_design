# Suggestions demo

Run the backend, sign in, upload a dataset (`POST /api/analyze`), save one or
more comparisons, then request suggestions. Replace `$ID` with the report id
and keep the session cookie (`-b cookies.txt`).

```bash
# All findings, first page
curl -s -b cookies.txt -X POST http://localhost:8000/api/reports/$ID/suggestions

# Only selected comparisons, second page of two
curl -s -b cookies.txt -X POST http://localhost:8000/api/reports/$ID/suggestions \
  -H 'Content-Type: application/json' \
  -d '{"comparison_ids": [3, 4], "limit": 2, "offset": 2}'
```

With no `ANTHROPIC_API_KEY` the response has `"source": "fallback"`. To see AI
wording set the key (and install `anthropic`) before starting the backend;
`"source"` becomes `"ai"` only if the reply passes validation.

## Expected results

Stored samples in `docs/examples/suggestions/` are produced by the endpoint
and checked by `test/test_suggestion_schema.py`.

| Sample | Expected finding types, in order |
| --- | --- |
| `ranked_with_warnings.json` | missing_values, group_difference, duplicates |
| `paged_second_page.json` | duplicates (offset 2) |
| `exploratory_comparisons.json` | missing_values, group_difference, duplicates, group_difference (both comparisons `exploratory`) |
| `unavailable_test.json` | small_groups (evidence table, no conclusion) |
| `non_significant.json` | group_difference (reads "did not detect a difference") |
| `clean_report.json` | none |
| `ai_source.json` | missing_values, duplicates, `source: "ai"` |

## Checks

```bash
python -m pytest test/test_api_suggestions.py test/test_suggestions_rules.py test/test_suggestion_schema.py
```

Covers ownership and cross-report rejection, clean and older reports,
reproducible order, paging, exploratory marking, fallback with no credentials,
and rejection of invalid AI output.

## Still to verify with real data

* Ticket #57: ANOVA and distribution results (see `docs/suggestions-ranking.md`
  section 6 for the shapes assumed). Until it lands these paths are covered only
  by tests on constructed results.
* Ticket #90: the relationship explorer rendering `visual` specs.
