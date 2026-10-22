# Suggestions frontend contract

The report interface expects the Ticket #47 backend at:

`POST /api/reports/{analysis_id}/suggestions`

The operation must require the existing authenticated session and return 404
when the report is missing or belongs to another user. The response shape is:

```json
{
  "analysis_id": 42,
  "source": "ai",
  "suggestions": [
    {
      "title": "Review missing age values",
      "affected_columns": ["age"],
      "explanation": "Age is missing in a material share of rows.",
      "evidence": ["18 of 120 rows are missing age (15.00%)."],
      "next_steps": ["Confirm why age is missing before choosing an imputation method."]
    }
  ]
}
```

`source` must be either `ai` or `fallback`. Every list must be present even
when empty. The frontend prevents duplicate submissions, supports retry and
empty results, aborts an in-flight request when the report changes, and
rejects a response whose `analysis_id` does not match the current report.
