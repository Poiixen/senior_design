# Cleaning previews

Ticket #54. A follow-up to the duplicate-rows finding: the user can see what
removing the duplicates would do. This is a **preview only**. The uploaded
dataset, the saved report and its diagnostics are never changed, and nothing
is applied or exported. Example responses are in
[examples/cleaning-previews/](examples/cleaning-previews/), generated from the
real API.

## Supported action

Only `remove_exact_duplicates`: a row identical to an earlier row in every
column is proposed for removal and the first occurrence is kept. This is the
same definition as the duplicate diagnostic, so `counts.removed_rows` always
equals the report's duplicate count.

- **Missing values:** two missing cells in the same column are equal. Rows with
  missing cells in the same places and equal values elsewhere are duplicates.
- **Row order:** kept rows keep their original order.
- **Row references:** 1-based positions among the data rows (header excluded),
  in file order. Only references are returned, never cell values.
- **Bounds:** at most 10 groups, each listing at most 10 removed rows.
  `groups_truncated` is true when groups were left out; `removed_count` is
  always the full count for that group.

## `POST /api/reports/{analysis_id}/cleaning-previews`

```json
{"action": "remove_exact_duplicates"}
```

Needs a logged-in session. `dataset_version` ties the preview to the analyzed
dataset (id, dimensions and a SHA-256 of the stored rows).

| Status | When |
| --- | --- |
| 200 | Preview computed. `status` is `ok`, or `no_duplicates` (zero rows would be removed, `groups` empty). `preview` is always `true` and `applied` always `false`. |
| 400 | Unsupported `action`. `detail` lists the supported ones. |
| 401 | Not logged in. |
| 404 | Report not found or not owned by the user. |
| 409 | The rows were not stored, or no longer match the analyzed dimensions. Upload the file again. |
| 422 | Malformed body (missing or non-string `action`). |
