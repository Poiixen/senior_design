import assert from "node:assert/strict";
import { test } from "node:test";
import { dashboardOverview, knownCount, reportDate } from "../frontend/app/lib/dashboard.ts";

function report(id, overrides = {}) {
  return { analysis_id: id, filename: `dataset-${id}.csv`, status: "completed",
    started_at: "2026-10-01T10:00:00Z", completed_at: "2026-10-01T10:01:00Z",
    dataset: { rows: 100, columns: 4 }, summary: { issues_detected: 0 }, ...overrides };
}

test("new accounts have zero totals and no latest report or date", () => {
  const result = dashboardOverview([]);
  assert.equal(result.total, 0);
  assert.equal(result.completed, 0);
  assert.equal(result.withIssues, 0);
  assert.equal(result.latest, null);
  assert.equal(result.latestAnalysisDate, null);
  assert.deepEqual(result.recent, []);
});

test("totals use all reports, while previews show only the five newest", () => {
  const reports = Array.from({ length: 8 }, (_, i) => report(i + 1, {
    completed_at: `2026-10-${String(i + 1).padStart(2, "0")}T10:00:00Z`,
    summary: { issues_detected: i % 2 ? 3 : 0 },
  }));
  const original = [...reports];
  const result = dashboardOverview(reports);
  assert.equal(result.total, 8);
  assert.equal(result.completed, 8);
  assert.equal(result.withIssues, 4);
  assert.deepEqual(result.recent.map(item => item.analysis_id), [8, 7, 6, 5, 4]);
  assert.equal(result.latestAnalysisDate, reports[7].completed_at);
  assert.deepEqual(reports, original);
});

test("failed and running reports are not counted as completed analyses", () => {
  const result = dashboardOverview([report(1), report(2, {
    status: "running", completed_at: null, started_at: "2026-10-27T10:00:00Z",
  }), report(3, { status: "failed", completed_at: "2026-10-26T10:00:00Z" })]);
  assert.equal(result.completed, 1);
  assert.equal(result.latest.analysis_id, 2);
  assert.equal(result.latestAnalysisDate, "2026-10-01T10:01:00Z");
});

test("older reports do not turn missing fields into zero or completed", () => {
  const result = dashboardOverview([report(1), report(2, {
    status: undefined, dataset: undefined, summary: undefined, started_at: null, completed_at: "bad date",
  }), report(3, { summary: { issues_detected: 2 } })]);
  assert.equal(result.completed, null);
  assert.equal(result.issuesUnavailable, 1);
  assert.equal(result.withIssues, 1);
  assert.equal(reportDate(result.recent.at(-1)), null);
  assert.equal(knownCount(undefined), null);
  assert.equal(knownCount(null), null);
  assert.equal(knownCount(-1), null);
  assert.equal(knownCount(NaN), null);
  assert.equal(knownCount(0), 0);
});

test("invalid completion dates fall back to started dates, with IDs breaking ties", () => {
  const reports = [report(1, { completed_at: "invalid" }), report(4, { completed_at: null }), report(2, { completed_at: null })];
  assert.equal(reportDate(reports[0]), reports[0].started_at);
  assert.deepEqual(dashboardOverview(reports).recent.map(item => item.analysis_id), [4, 2, 1]);
});
