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

test("all product pages redirect before returning HTML to anonymous visitors", async () => {
  const build = await import("../frontend/build/server/index.js");
  const handle = createRequestHandler(build, "production");
  for (const path of ["/", "/showcase", "/showcase/report", "/example-report", "/documentation", "/dashboard", "/upload", "/reports", "/reports/1", "/settings"]) {
    const response = await handle(new Request(`http://localhost${path}`));
    assert.equal(response.status, 302, path);
    assert.equal(response.headers.get("Location"), `/login?next=${encodeURIComponent(path)}`);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
    assert.doesNotMatch(await response.text(), /Turn messy datasets|Application navigation|ILLUSTRATIVE SAMPLE/);
  }
});

test("login, registration and verification remain reachable without a session", async () => {
  const build = await import("../frontend/build/server/index.js");
  const handle = createRequestHandler(build, "production");
  for (const path of ["/login", "/register", "/verify-email"]) {
    const response = await handle(new Request(`http://localhost${path}`));
    assert.equal(response.status, 200, path);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
  }
});

test("server gate verifies cookies with fixed API origin and fails closed", async (t) => {
  const build = await import("../frontend/build/server/index.js");
  const handle = createRequestHandler(build, "production");
  let status = 401;
  let requested;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    requested = { url: String(url), options };
    return new Response(JSON.stringify({ id: 1, email: "verified@example.com" }), {
      status, headers: { "Content-Type": "application/json", "Set-Cookie": "session=renewed; HttpOnly" },
    });
  });
  const request = () => new Request("http://untrusted-host.example/documentation", { headers: { Cookie: "session=opaque" } });
  let response = await handle(request());
  assert.equal(response.status, 302);
  assert.equal(requested.url, `${process.env.API_INTERNAL_URL || "http://127.0.0.1:8000"}/api/auth/me`);
  assert.equal(requested.options.headers.Cookie, "session=opaque");
  status = 503;
  response = await handle(request());
  assert.equal(response.status, 503);
  assert.doesNotMatch(await response.text(), /Public navigation|Application navigation/);
  status = 200;
  response = await handle(request());
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Set-Cookie"), "session=renewed; HttpOnly");
  assert.equal(response.headers.get("Cache-Control"), "no-store");
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
