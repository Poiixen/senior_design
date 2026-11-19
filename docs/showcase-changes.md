# Showcase tickets 64–67: implementation and handoff

Source: `Team_Science_Showcase_GitHub_Issues.csv` and all four scanned pages of
`DOC.pdf`, visually reviewed on November 18, 2026. The demo now follows the
meeting guidance: a short takeaway and one next step first; statistical methods
and numbers are available on demand. The underlying results are unchanged.

Chosen production address: **https://spteamscience.com/**.
Poster destination: **https://spteamscience.com/showcase**.
These are intended addresses, not a claim that the site is live. The owner is
purchasing the domain and will follow [deployment.md](deployment.md).

## Ticket 64 — report interpretation

- Fixed a mismatch where a Holm-adjusted significance decision could accompany
  a raw p-value in the explanation. Evidence retains raw values and now identifies
  adjusted values and the count of distinct selected saved comparisons.
- Explained Holm's false-positive correction and its limited scope, Cohen's d
  and half-SD example, and Cramer's V's scale, direction/causality limitations.
- Explained IQR fences and zero-IQR behavior, including concentrated/discrete
  columns. Flags remain review prompts, not automatic exclusions.
- Elevated expected-count reliability caveats and the changed hypothesis when
  combining categories. No percentile substitute is recommended.
- Named the actual saved visual in each first next step; evidence-table findings
  explicitly say no chart is available. Existing UI renders that visual beside
  the finding and supplies an accessible table if it cannot draw the chart.
- Tiny p-values display with a threshold; full numeric precision stays in API
  evidence. Optional AI can edit titles and additional next steps, while statistical
  explanations and the first visual instruction remain deterministic.

### PDF review completed

| Page / comment | Resolution |
| --- | --- |
| 1: What is Holm's method? | Short takeaway avoids jargon. Statistical details explain false-positive correction, selected comparison scope, family size, raw and adjusted p-values. |
| 1: What does Cohen's d provide? | Details explain pooled standard deviations and a half-SD example. Magnitude remains distinct from practical importance, which depends on the user's question. |
| 1, 2, 4: Which chart? | Every chart control names its actual saved visual; missing visuals explicitly fall back to a table. Comparisons show their chart in the opened comparison. |
| 2, 4: What is Cramer's V / Cohen's benchmark? | Details explain categorical association strength, table-size-qualified magnitude labels, and no direction or causal inference. |
| 3: What is a percentile rule / why use one? | Removed the unexplained alternative from recommendations. Documentation defines 1st/99th percentiles only as a separate optional exploratory rule, never a superior default. |
| 3: Duplicate EVIDENCE heading | A single Statistical details disclosure contains supporting evidence; no duplicate EVIDENCE labels. |
| 3: Concentrated hours / zero-IQR capital gain | Full IQR explanation retained; short summaries say flags are not mistakes and explain why equal middle values flag every different value. |
| 4: Sparse expected counts / tiny p-values | A short reliability caution stays visible even when details are closed. Display uses `p < 0.001`; numeric API evidence is preserved. |

### Less text for visitors

- Added deterministic `plain_summary`, `recommended_action`, and `plain_caution`
  fields. Optional AI cannot replace these or the detailed statistical explanation.
- Shared finding cards lead with a short takeaway and one action. Named charts,
  statistical explanations and complete numbers expand separately.
- Demo comparisons are shown once. The suggestions section shows at most three
  quality findings initially, with additional findings behind More findings.
- Replaced the long dashboard preview with three short counts and simplified entry
  instructions. Important reliability cautions remain visible; technical methods
  are not required reading.
- Kept keyboard-operable native disclosures, 44px controls, readable chart labels,
  and mobile-safe nested tables/charts.

Before/after screenshots are linked in [review evidence](showcase-review.md).

## Ticket 65 — deployment preparation

Added an API Dockerfile, Compose stack, Caddy proxy, private API/frontend networking,
persistent data/TLS volumes, upload/request/resource safeguards and bounded logs.
Added credential input lengths and PATCH to credentialed CORS methods. Environment
files are excluded from Git and image build contexts. Production dependencies and
builds use the existing frontend Dockerfile.

Follow [deployment.md](deployment.md). The public URL, real-device workflow,
restart/redeploy persistence, backup restore, CI result on GitHub, and protected
production promotion remain owner-run acceptance checks. No infrastructure was purchased.

## Ticket 66 — visitor flow

Added `/showcase` and `/showcase/report`, with one-tap entry, read-only synthetic
data guidance, overview, saved comparison expanders, charts, and suggestions.
Kept existing routes. Added touch-friendly wrapping layout, loading/error states,
bounded demo requests and a session recovery link. The landing page links to the demo.
The five-minute idle policy remains; an expired demo session returns to entry.

The actual `production` branch must start at reviewed green `main`; this checkout
started on `prod`. Branch protection and QR publication are documented rather
than silently applied to the repository. Physical camera/device validation remains.

## Ticket 67 — repeatable protected demo

`python -m scripts.seed_showcase` creates an offline random-password demo user,
an 83-row synthetic workshop dataset, one report and two saved comparisons.
Rows are invented by this project's generator; there is no external dataset,
personal information, or UCI Adult attribution requirement. Measures are minutes,
completion and ratings by workshop time. Missing ratings, repeated rows and an
unusual duration deliberately demonstrate diagnostics; no intervention is implied.

Repeat seeding reuses records and repairs a missing Parquet copy. Demo identity
uses a reserved server-created dataset source marker, not a client-provided role.
The auth dependency blocks all authenticated non-read operations for that identity
except suggestions; suggestions remain deterministic. Ownership checks still
restrict every report. Chat and writes return an explanatory 403. The simplified
showcase does not offer these actions; full report pages may show controls whose
attempted writes are rejected. No demo password or AI key is exposed to visitors.

Offline seeding is single-operator maintenance, not a concurrent public endpoint.
The prepared dataset is restored by rerunning the seed. A full reset uses a fresh
staging volume; do not destroy production data to reset a demo.

## Verification

Backend regression coverage is
in `test/test_showcase.py` and statistical wording tests. Mobile browser tests use
mock API responses to isolate layout/navigation; backend tests separately exercise
real seeding and permissions. Their fixture is generated by
`python -m scripts.build_showcase_example` using temporary SQLite/Parquet storage
and the actual seed and suggestions services. They do not prove live TLS, DNS or
physical phone behavior.

Validation performed locally:

- Existing backend suite: 668 passed, one Windows permission-test skip, ten
  integration tests deselected. SciPy emits its expected constant-data warning.
- Final focused showcase, suggestion, statistical-edge and rate-limit suite: 151 passed.
- Frontend production build and TypeScript check passed; 20 existing Node tests passed.
- All 28 browser tests passed, including showcase widths 320/375/390/768/1440,
  expandable details, chart expansion, refresh, expired session recovery, unavailable
  entry, and existing report/navigation workflows.
- API and frontend Docker images built locally; the frontend container served the
  homepage and both showcase routes successfully. Caddy validated the chosen domain
  configuration. Container tests checked health, secure cookies, demo entry, read-only
  restrictions, two comparisons, deterministic guidance, and persisted data across
  replacement containers using an isolated test volume.

Screenshots are generated under `.run/playwright-results`; selected before/after
captures are retained in `docs/review/showcase/`. CI uploads current captures as
`showcase-browser-evidence`. No PR has been published or issues closed.

## Remaining owner-run release checks

- Finish domain purchase, provision hosting, and apply the documented DNS records.
- Verify live HTTPS, both hostnames, personal upload/login, and a phone on cellular.
- Test physical iOS/Android cameras before printing the final QR.
- Promote reviewed green `main` to protected `production` and verify GitHub CI.
- Perform the documented off-server backup and restore rehearsal.

These external release steps remain separate from completed repository changes;
no hosting resources, DNS records, or domain purchases were created here.
