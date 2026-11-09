import { test, expect, type Page } from "@playwright/test";
import { readFileSync, readdirSync } from "node:fs";
import { sampleReport } from "../app/lib/sample-report";

const fixture = (path: string) => JSON.parse(readFileSync(new URL(`../../docs/examples/${path}`, import.meta.url), "utf8")).response;
const regrouped = fixture("regrouping/method_change.json");
const numerical = fixture("numeric-pack/responses/two_groups_known_difference.json");
const ranked = fixture("suggestions/ranked_with_warnings.json");
const categorical = sampleReport.column_profiles!.find(p => p.name === "group")!;
const report = { ...sampleReport, analysis_id: 1, filename: "weekly-demo.csv", column_profiles: [
  ...sampleReport.column_profiles!,
  { ...categorical, name: "education", identifier_review: { reasons: ["Review whether these labels are meaningful groups."] }, distribution: {
    distinct_categories: 4, total_rows: 60, non_missing_rows: 60, missing_rows: 0, percentage_denominator: "non_missing_rows",
    categories: regrouped.regrouping.columns[0].before.map((r: { label: string; count: number }) => ({ ...r, percentage: r.count / 60 * 100 })), categories_truncated: false, omitted_categories: 0, omitted_count: 0,
  } },
] , correlation: { columns: ["age", "score"], matrix: [[1, .8], [.8, 1]] } };

async function setup(page: Page, saved: any[] = []) {
  const selections: any[] = [];
  let questions: any[] = [], history: any[] = [], failAnswer = false;
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const id = Number(path.split("/")[3]);
    if (path === "/api/auth/me") return route.fulfill({ json: { id: 9, email: "demo@example.test" } });
    if (path === "/api/reports") return route.fulfill({ json: { reports: [report, { ...report, analysis_id: 2, filename: "other.csv" }] } });
    if (/\/reports\/\d+$/.test(path)) return route.fulfill({ json: { ...report, analysis_id: id } });
    if (path.endsWith("/comparisons")) {
      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON(); selections.push(body);
        const result = { ...(body.category_mappings?.education ? regrouped : numerical), analysis_id: id, comparison_id: saved.length + 1 };
        saved.push(result); return route.fulfill({ status: 201, json: result });
      }
      return route.fulfill({ json: { comparisons: saved.map(r => ({ ...r, analysis_id: id })) } });
    }
    if (path.endsWith("/suggestions")) {
      const body = route.request().postDataJSON(); selections.push(body);
      const suggestions = Array.from({ length: 7 }, (_, i) => ({ ...ranked.suggestions[i % ranked.suggestions.length], finding_id: `finding-${i}`, title: `Rank ${i + 1}: ${ranked.suggestions[i % ranked.suggestions.length].title}` }));
      return route.fulfill({ json: { ...ranked, source: body.offset ? "fallback" : "ai", analysis_id: id, suggestions: suggestions.slice(body.offset, body.offset + body.limit), total_findings: 7, has_more: body.offset + body.limit < 7, evidence_fingerprint: "same-evidence", comparison_ids_used: body.comparison_ids } });
    }
    if (path.endsWith("/conversations")) return route.fulfill({ json: { analysis_id: id, conversations: id === 1 && history.length ? [{ conversation_id: 10, first_question: "Which result supports this?" }] : [] } });
    if (path.endsWith("/conversations/10")) return route.fulfill({ json: { analysis_id: id, conversation_id: 10, messages: history } });
    if (path.endsWith("/questions")) {
      const body = route.request().postDataJSON(); questions.push(body);
      const user = { message_id: 1, role: "user", content: body.question, request_id: body.request_id, sources: [] };
      const assistant = { message_id: 2, role: "assistant", content: "The saved Welch comparison supports this answer.", request_id: body.request_id, sources: [{ source_id: "comparison:1", label: "Welch comparison", comparison_id: 1 }] };
      history = failAnswer ? [user] : [user, assistant];
      return route.fulfill({ json: { analysis_id: id, conversation_id: 10, status: failAnswer ? "unavailable" : "answered", user_message: user, assistant_message: failAnswer ? null : assistant, unavailable_reason: failAnswer ? "AI is temporarily unavailable." : null } });
    }
    if (path.endsWith("/duplicate-preview")) return route.fulfill({ json: { analysis_id: id, original_rows: 20, proposed_removed_rows: 1, resulting_rows: 19, definition: "Exact matches across all source columns; keep the first occurrence.", note: "Preview only. No changes were applied." } });
    return route.fulfill({ status: 404, json: { detail: "Unavailable" } });
  });
  return { selections, questions, failAnswer: (value: boolean) => { failAnswer = value; } };
}
const tab = (page: Page, name: string) => page.getByRole("navigation", { name: "Report views" }).getByRole("link", { name, exact: true });

test("numerical selection, exact regrouping, saved retrieval and freshness", async ({ page }) => {
  const state = await setup(page, [{ ...numerical, comparison_id: 1 }]);
  await page.goto("/reports/1");
  await page.getByRole("button", { name: "Generate suggestions", exact: true }).click();
  await expect(page.locator(".suggestion-card")).toHaveCount(5);
  await tab(page, "Columns").click();
  await page.getByRole("combobox", { name: "Grouping column", exact: true }).selectOption("education");
  await page.getByRole("combobox", { name: "Numerical measurement", exact: true }).selectOption("age");
  await page.getByText("Category counts and regrouping: education", { exact: true }).click();
  await page.getByLabel("BA (string; n=25)", { exact: true }).check();
  await page.getByLabel("MA (string; n=3)", { exact: true }).check();
  await page.getByLabel("PhD (string; n=2)", { exact: true }).check();
  await page.getByLabel("Combined label", { exact: true }).fill("Degree");
  await page.getByRole("button", { name: "Add mapping to preview" }).click();
  await expect(page.getByText("Mapping preview", { exact: true })).toBeVisible();
  await page.getByLabel(/I reviewed education/).check();
  await page.getByRole("button", { name: "Run comparison", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Exact saved category mapping" })).toBeVisible();
  expect(state.selections.at(-1)).toMatchObject({ method: "auto", group_column: "education", value_column: "age", category_mappings: { education: [{ label: "Degree", categories: ["BA", "MA", "PhD"] }] }, confirm_columns: ["education"] });
  await expect(page.getByText(/The number of groups changed from 4 to 2/)).toBeVisible();
  await expect(page.locator(".evidence-bars").getByText("After: Degree")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Exact saved category mapping" })).toBeVisible();
  await tab(page, "Overview").click();
  await page.getByRole("button", { name: "Generate suggestions", exact: true }).click();
  await tab(page, "Columns").click();
  await page.getByRole("combobox", { name: "Analysis method", exact: true }).selectOption("welch_anova");
  await tab(page, "Overview").click();
  await expect(page.getByText(/Outdated findings:/)).toBeVisible();
  await expect(page.getByRole("button", { name: "View more findings" })).toBeDisabled();
  await page.getByRole("button", { name: "Regenerate suggestions" }).click();
  await expect(page.getByText(/Outdated findings:/)).toHaveCount(0);
});

test("ranked cards expand in backend order and link to the saved evidence", async ({ page }) => {
  await setup(page, [{ ...numerical, comparison_id: 1 }]);
  await page.goto("/reports/1");
  await page.getByRole("button", { name: "Generate suggestions", exact: true }).click();
  await expect(page.locator(".suggestion-card")).toHaveCount(5);
  await page.getByRole("button", { name: "View more findings" }).click();
  await expect(page.locator(".suggestion-card")).toHaveCount(7);
  await expect(page.locator(".suggestion-card").first().getByText("AI-generated", { exact: true })).toBeVisible();
  await expect(page.locator(".suggestion-card").last().getByText("Fallback guidance", { exact: true })).toBeVisible();
  const titles = await page.locator(".suggestion-card h3").allTextContents();
  expect(titles.map(t => t.match(/^Rank (\d+)/)![1])).toEqual(["1", "2", "3", "4", "5", "6", "7"]);
  await expect(page.locator(".evidence-visual").first()).toBeVisible();
  const link = page.getByRole("link", { name: /Inspect result #1/ }).first();
  await link.click();
  await expect(page.locator("#comparison-1")).toBeVisible();
  await expect(page.getByText(/^95% confidence interval for the mean difference/)).toBeVisible();
  await page.screenshot({ path: "../.run/relationship-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../.run/relationship-mobile.png", fullPage: true });
});

test("chat retries reuse the turn, restore history and keep previews read-only", async ({ page }) => {
  const state = await setup(page, [{ ...numerical, comparison_id: 1 }]);
  state.failAnswer(true);
  await page.goto("/reports/1");
  await page.getByLabel("Follow-up question").fill("Which result supports this?");
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  await expect(page.getByText("AI is temporarily unavailable.", { exact: false })).toBeVisible();
  state.failAnswer(false);
  await page.getByRole("button", { name: "Retry question" }).click();
  await expect(page.getByText("The saved Welch comparison supports this answer.")).toBeVisible();
  expect(state.questions[0].request_id).toBe(state.questions[1].request_id);
  await expect(page.locator(".chat-messages article")).toHaveCount(2);
  await page.reload();
  await expect(page.getByText("The saved Welch comparison supports this answer.")).toBeVisible();
  await page.getByRole("button", { name: "Preview duplicate removal" }).click();
  await expect(page.getByText("Preview only. No changes were applied.", { exact: true })).toBeVisible();
  await expect(page.locator(".duplicate-preview dd")).toHaveText(["20", "1", "19"]);
  await expect(page.getByRole("button", { name: /apply/i })).toHaveCount(0);
  await page.getByRole("button", { name: "Start new conversation" }).click();
  await expect(page.locator(".chat-messages article")).toHaveCount(0);
  await page.getByLabel("Conversation history").selectOption("10");
  await expect(page.locator(".chat-messages article")).toHaveCount(2);
  await page.goto("/reports/2");
  await expect(page.locator(".chat-messages article")).toHaveCount(0);
  await expect(page.locator(".duplicate-preview dd")).toHaveCount(0);
});

test("shared numerical pack and sparse categorical results remain readable", async ({ page }) => {
  test.setTimeout(90_000);
  const directory = new URL("../../docs/examples/numeric-pack/responses/", import.meta.url);
  const results = readdirSync(directory).map(name => fixture(`numeric-pack/responses/${name}`)).filter(r => r.comparison_type).map((r, i) => ({ ...r, comparison_id: i + 1 }));
  results.push({ ...fixture("regrouping/sparse_comparison.json"), comparison_id: results.length + 1 });
  await setup(page, results);
  await page.goto("/reports/1?view=columns");
  for (const r of results) {
    await page.getByLabel("Open saved result").selectOption(String(r.comparison_id));
    const card = page.locator(`#comparison-${r.comparison_id}`);
    await expect(card).toBeVisible();
    if (r.test.status === "unavailable") await expect(card.getByText(r.test.reason, { exact: true })).toBeVisible();
    if (r.comparison_type === "categorical_numeric" && r.groups?.length) {
      const rows = card.locator("table").last().locator("tbody tr");
      await expect(rows).toHaveCount(r.groups.length);
      expect(await rows.first().locator("td").first().textContent()).toBe(String(r.groups[0].count));
    }
    for (const warning of r.warnings) await expect(card.getByText(warning, { exact: true })).toBeVisible();
    await expect(card).not.toContainText("NaN");
  }
});

test("older reports and unknown visual specifications use factual fallbacks", async ({ page }) => {
  await setup(page);
  await page.route("**/api/reports/1/suggestions", route => route.fulfill({ json: { analysis_id: 1, source: "fallback", suggestions: [{ title: "Older evidence", explanation: "Only a count was saved.", affected_columns: [], evidence: ["4 rows"], next_steps: ["Review the source."], visual: { chart_type: "future_chart", title: "Saved count", data: { count: 4 }, warnings: [] } }] } }));
  await page.goto("/reports/1");
  await page.getByRole("button", { name: "Generate suggestions", exact: true }).click();
  await expect(page.getByText(/Chart evidence is unavailable or this visual type/)).toBeVisible();
  await expect(page.locator(".evidence-visual table")).toContainText("4");
  await tab(page, "Columns").click();
  await page.getByRole("button", { name: "Details for age", exact: true }).click();
  await expect(page.getByText(/Actual whisker endpoints were not saved/)).toBeVisible();
});

test("late suggestions and answers cannot leak into another report", async ({ page }) => {
  await setup(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/reports/1/suggestions", async route => {
    await gate;
    await route.fulfill({ json: { analysis_id: 1, source: "fallback", suggestions: [{ title: "Report one only", explanation: "Old context", evidence: [], affected_columns: [], next_steps: [] }] } }).catch(() => {});
  });
  await page.route("**/api/reports/1/questions", async route => {
    await gate;
    await route.fulfill({ json: { analysis_id: 1, conversation_id: 42, status: "unavailable", user_message: { message_id: 1, role: "user", content: "Private question for report one", request_id: "old", sources: [] } } }).catch(() => {});
  });
  await page.goto("/reports/1");
  await page.getByRole("button", { name: "Generate suggestions", exact: true }).click();
  await page.getByLabel("Follow-up question").fill("Private question for report one");
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  await page.getByRole("link", { name: "Saved Reports", exact: true }).click();
  await page.getByRole("link", { name: "other.csv", exact: true }).click();
  await expect(page.getByRole("button", { name: "Generate suggestions", exact: true })).toBeEnabled();
  release();
  await page.getByRole("button", { name: "Generate suggestions", exact: true }).click();
  await expect(page.locator(".suggestion-card")).toHaveCount(5);
  await expect(page.getByText("Report one only")).toHaveCount(0);
  await expect(page.getByText("Private question for report one")).toHaveCount(0);
  await expect(page.locator(".chat-messages article")).toHaveCount(0);
});

test("empty findings, suggestion retries and unavailable duplicate sources stay usable", async ({ page }) => {
  await setup(page);
  let attempts = 0;
  await page.route("**/api/reports/1/suggestions", route => ++attempts === 1
    ? route.fulfill({ status: 503, json: { detail: "Suggestions temporarily unavailable." } })
    : route.fulfill({ json: { analysis_id: 1, source: "fallback", suggestions: [] } }));
  await page.route("**/api/reports/1/duplicate-preview", route => route.fulfill({ status: 409, json: { detail: "Source rows are unavailable for this older report." } }));
  await page.goto("/reports/1");
  await page.getByRole("button", { name: "Generate suggestions", exact: true }).click();
  await page.locator(".suggestions-panel").getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByText("No noteworthy findings were returned for this report.")).toBeVisible();
  await page.getByRole("button", { name: "Preview duplicate removal" }).click();
  await expect(page.getByText("Source rows are unavailable for this older report.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry duplicate preview" })).toBeEnabled();
  await tab(page, "Columns").click();
  await expect(page.getByRole("heading", { name: "Numerical correlations" })).toBeVisible();
});

test("all supporting visual kinds render backend values and evidence tables", async ({ page }) => {
  await setup(page);
  const specs = [
    { chart_type: "bar", title: "Missing values", data: { categories: ["Missing", "Present"], values: [3, 15] }, units: "rows", percent_denominator: "all 18 rows" },
    { chart_type: "histogram", title: "Distribution", data: { bin_edges: [0, 10, 20], counts: [4, 14] }, x_label: "score" },
    { chart_type: "box_plot", title: "Numeric box", data: { ...numerical.groups[0] }, y_label: "score" },
    { chart_type: "grouped_box", title: "Group boxes", data: { groups: numerical.groups }, y_label: "score" },
    { chart_type: "grouped_percentage_bar", title: "Category percentages", data: { group_categories: ["A"], outcome_categories: ["yes", "no"], counts: [[3, 7]], row_percentages: [[30, 70]] }, percent_denominator: "group_total" },
    { chart_type: "contingency_heatmap", title: "Category heatmap", data: { group_categories: ["A"], outcome_categories: ["yes", "no"], counts: [[3, 7]] }, units: "rows" },
    { chart_type: "correlation_pair", title: "Focused correlation", data: { columns: ["age", "score"], value: .8 }, x_label: "age", y_label: "score" },
    { chart_type: "before_after_bar", title: "Category changes", data: { before: [{ label: "B", count: 6 }, { label: "C", count: 6 }], after: [{ label: "BC", count: 12 }] }, units: "rows" },
    { chart_type: "evidence_table", title: "Unavailable chart", data: { rows: [{ label: "n", value: 1 }] }, fallback_reason: "Not enough saved observations." },
  ];
  await page.route("**/api/reports/1/suggestions", route => route.fulfill({ json: { analysis_id: 1, source: "fallback", suggestions: specs.map((visual, i) => ({ finding_id: `visual-${i}`, title: visual.title, explanation: "Review the saved evidence.", affected_columns: [], evidence: [], next_steps: [], visual })) } }));
  await page.goto("/reports/1");
  await page.getByRole("button", { name: "Generate suggestions", exact: true }).click();
  await expect(page.locator(".evidence-visual")).toHaveCount(9);
  await expect(page.locator(".histogram-chart svg")).toHaveCount(1);
  await expect(page.getByText("Included values: 18.", { exact: false })).toBeVisible();
  await expect(page.getByText("After: BC", { exact: true })).toBeVisible();
  await expect(page.getByText("Not enough saved observations.")).toBeVisible();
  await page.screenshot({ path: "../.run/worth-noting-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "../.run/worth-noting-mobile.png", fullPage: true });
});
