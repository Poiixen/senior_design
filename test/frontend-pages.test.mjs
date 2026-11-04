// `npm.cmd test` in frontend builds the application before running these checks.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";
import { routes } from "../frontend/build/server/index.js";

const requireFrontend = createRequire(new URL("../frontend/package.json", import.meta.url));
const { createElement } = requireFrontend("react");
const { renderToStaticMarkup } = requireFrontend("react-dom/server");
const { createMemoryRouter, RouterProvider, createRequestHandler } = requireFrontend("react-router");
const { sampleReport } = await import("../frontend/app/lib/sample-report.ts");

function renderReport(report, path = "/reports/7") {
  const router = createMemoryRouter([{ id: "report", path: "/reports/:analysisId", Component: routes["routes/report"].module.default }], {
    initialEntries: [path], hydrationData: { loaderData: { report: { report, isSample: false } } },
  });
  return renderToStaticMarkup(createElement(RouterProvider, { router }));
}

test("the default route serves the public homepage without blocking on authentication", async () => {
  const build = await import("../frontend/build/server/index.js");
  const response = await createRequestHandler(build, "production")(new Request("http://localhost/"));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Location"), null);
  const html = await response.text();
  assert.match(html, /Turn messy datasets/);
  assert.match(html, /Sign in/);
  assert.doesNotMatch(html, /My account|Log out/);
  assert.match(html, /ILLUSTRATIVE SAMPLE/);
  assert.match(html, /href="\/example-report"/);
  assert.doesNotMatch(html, /class="sidebar"/);
  assert.doesNotMatch(html, /href="\/(?:dashboard|upload|reports|settings)(?:[/?"])/);
  assert.equal(build.assets.routes["routes/home"].hasClientLoader, false);
  assert.ok(routes["routes/dashboard"]);
  assert.ok(routes["routes/upload"]);
});

test("public example and documentation render without workspace navigation", async () => {
  const build = await import("../frontend/build/server/index.js");
  const handle = createRequestHandler(build, "production");
  for (const path of ["/example-report", "/example-report?view=columns", "/documentation"]) {
    const response = await handle(new Request(`http://localhost${path}`));
    assert.equal(response.status, 200);
    const html = await response.text();
    assert.match(html, /Public navigation/);
    assert.doesNotMatch(html, /Application navigation|href="\/(?:dashboard|upload|reports|settings)(?:[/?"])/);
  }
  const legacy = await handle(new Request("http://localhost/reports/sample?view=missing"));
  assert.equal(legacy.headers.get("Location"), "/example-report?view=missing");
});

test("workspace HTML waits for session verification before rendering navigation", async () => {
  const build = await import("../frontend/build/server/index.js");
  const handle = createRequestHandler(build, "production");
  for (const path of ["/dashboard", "/upload", "/reports", "/reports/1", "/settings"]) {
    const response = await handle(new Request(`http://localhost${path}`));
    const html = await response.text();
    assert.match(html, /Checking your session/);
    assert.doesNotMatch(html, /Application navigation|class="workspace"/);
  }
});

test("analysis overview renders actual metrics and findings without inventing a quality score", () => {
  const html = renderReport({ ...sampleReport, filename: "my-real-dataset.xlsx", analysis_id: 7 });
  assert.match(html, /my-real-dataset.xlsx/);
  assert.match(html, /Column types/);
  assert.match(html, /Key findings/);
  assert.match(html, /Column highlights/);
  assert.match(html, /100% of rows are missing a value/);
  assert.match(html, /2 values fall outside the expected range/);
  assert.match(html, /Export report/);
  assert.doesNotMatch(html, /Data quality score/);
  for (const view of ["columns", "missing", "duplicates", "outliers"]) {
    assert.match(html, new RegExp(`href="/reports/7\\?view=${view}"`));
  }
});

test("reports without newer column profiles retain a clear unavailable state", () => {
  const html = renderReport({ ...sampleReport, column_profiles: undefined });
  assert.match(html, /Column highlights are unavailable for this older report/);
  assert.match(html, /View all columns/);
});

test("empty completed datasets display no findings and finite chart labels", () => {
  const html = renderReport({ ...sampleReport, dataset: { rows: 0, columns: 0 },
    summary: { issues_detected: 0, numeric_columns: 0, categorical_columns: 0, duplicate_rows: 0, missing_columns: 0, outlier_columns: 0 },
    missing_values: [], outliers: [], column_profiles: [], validation: { valid: true, errors: [], warnings: [] } });
  assert.match(html, /No missing-value, duplicate, or outlier findings were detected/);
  assert.doesNotMatch(html, /NaN|Infinity/);
});

test("incomplete analyses keep their status and do not claim successful checks", () => {
  const html = renderReport({ ...sampleReport, status: "failed", missing_values: [], outliers: [],
    summary: { ...sampleReport.summary, duplicate_rows: 0 } });
  assert.match(html, /Analysis failed/);
  assert.match(html, /This analysis did not complete/);
  assert.match(html, /Findings may not yet be available/);
});

test("detailed diagnostic views are still available after the redesign", () => {
  for (const view of ["missing", "duplicates", "outliers"]) {
    const html = renderReport(sampleReport, `/reports/7?view=${view}`);
    assert.match(html, new RegExp(`aria-current="page" href="/reports/7\\?view=${view}"`));
    assert.doesNotMatch(html, /class="analysis-overview /);
  }
});
