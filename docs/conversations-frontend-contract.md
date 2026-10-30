# Report follow-up questions: frontend contract

Ticket #53. Users ask follow-up questions about a saved report and its
suggestions. Answers come only from the report's saved results. Models live in
`backend/models/conversations.py`; runnable samples are in
`docs/examples/conversations/` (regenerate with
`python scripts/build_conversation_samples.py`).

Every endpoint requires the existing authenticated session. A report or
conversation that is missing, belongs to another user, or belongs to a
different report is a **404** (`Report not found.` or `Conversation not found.`),
so ownership is checked before any report data or history is loaded.

## Endpoints

| Method and path | Purpose |
|---|---|
| `POST /api/reports/{analysis_id}/questions` | Ask a question (starts a thread when `conversation_id` is omitted). |
| `POST /api/reports/{analysis_id}/conversations` | Start an empty thread (201). |
| `GET /api/reports/{analysis_id}/conversations` | This user's threads for the report, newest first. |
| `GET /api/reports/{analysis_id}/conversations/{conversation_id}` | Every saved message, oldest first. |

### Ask

```json
{ "question": "Why was the group difference flagged?",
  "request_id": "q-1",
  "conversation_id": 3 }
```

- `question`: 1-1000 characters.
- `request_id`: required, 1-64 characters of `A-Z a-z 0-9 _ . : -`. Generate
  one per question and **reuse it when retrying** the same question.
- `conversation_id`: optional. Omit it to start a new thread.

Response (`QuestionResponse`):

| Field | Meaning |
|---|---|
| `status` | `answered`, `insufficient_evidence` or `unavailable`. |
| `conversation_id` | Thread the turn belongs to (new when none was sent). |
| `user_message` | The saved question. Always present. |
| `assistant_message` | The saved answer, or `null` when `status` is `unavailable`. |
| `unavailable_reason` | Plain-language reason when `status` is `unavailable`. |
| `replayed` | `true` when the stored answer for this `request_id` was returned unchanged. |

A message has `message_id`, `role` (`user` or `assistant`), `content`,
`request_id`, `created_at`, and, for assistant messages, `status` and `sources`.

### Sources

Each substantive answer lists the saved results it relied on. Sources are set
by the backend from ids the model picked from the evidence it was given; the
model cannot invent one.

```json
{ "source_id": "comparison:12", "kind": "comparison",
  "label": "Comparison 12: group and score",
  "comparison_id": 12, "method": "Welch's independent-samples t-test" }
```

`kind` is `finding` (a ranked finding from the suggestions endpoint, with
`finding_id`), `comparison` (a saved comparison, categorical or grouped
numeric) or `report` (the saved report overview). An answer with
`insufficient_evidence` has no sources.

## Statuses

- **answered**: grounded in at least one source.
- **insufficient_evidence**: the report does not contain what the question
  needs (including analyses that were not run, or questions unrelated to the
  report). The answer says so. This is an honest limitation, not an error.
- **unavailable**: no answer was produced: no AI credentials, a provider error
  or timeout, or a reply that failed validation. It is still HTTP 200. The
  question is saved; show a retry button.

## Retries

Retry with the **same `request_id`** (and the `conversation_id` you received).

- Question already answered: the stored answer is returned with
  `replayed: true`; the model is not called and nothing new is saved.
- Previous attempt was `unavailable`: the saved question is reused (same
  `message_id`) and the model is asked again. The question is never saved twice.
- Without `conversation_id`, a retry finds the thread that already holds that
  `request_id`, so no second thread is created.
- The same `request_id` with a different question is a **409**.

## Limits and timeouts

| Limit | Value |
|---|---|
| Question length | 1000 characters |
| Answer length | 2000 characters; longer replies are discarded |
| History sent to the model | last 6 messages, each cut to 600 characters |
| Findings sent | top 10 ranked findings |
| Comparisons sent | 10 most recent saved comparisons, 12 groups each |
| Model timeout | 15 seconds, no automatic retry (same client as suggestions) |
| Sources per answer | at most 8 |

Credentials (`ANTHROPIC_API_KEY`, optional `SUGGESTIONS_AI_MODEL`) stay on the
backend and never appear in a response.

## What the model receives, and how its reply is checked

It receives the question, the limited history, and compact aggregates only:
the report's row and column counts, the ranked findings (the same ones
`/suggestions` returns, deterministic wording), the saved comparisons'
statistics, group summaries, warnings and regrouping details, and the list of
analyses that were not run. It never receives dataset rows or example cell
values. The question, history, column names and group labels are all passed as
data inside JSON, and the system prompt tells the model to ignore any
instruction found there.

A reply is used only if all of these hold; otherwise the status is
`unavailable` and nothing is saved as an answer:

1. It is valid JSON with `sufficient_evidence`, `answer` and `source_ids`.
2. Every `source_id` was in the evidence it was sent, and a sufficient answer
   cites at least one.
3. Every number in the answer appears in the evidence it was sent (no
   invented calculations).
4. It contains none of the phrases the suggestions wording also bans (causal,
   fairness and delete/remove language).
5. It is within the length limit.

Statistical calculations are never done by the model.
