import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";


const { report, suggestions } = JSON.parse(readFileSync(new URL("../../docs/examples/showcase.json", import.meta.url), "utf8"));

for (const width of [320, 375, 390, 768, 1440]) {
  test(`showcase entry, chart, refresh and layout at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    let signedIn = false;
    await page.route("**/api/**", route => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/demo") { signedIn = true; return route.fulfill({ json: { analysis_id: 1 } }); }
      if (path === "/api/auth/me") return route.fulfill(signedIn ? { json: { id: 1, email: "showcase@demo.invalid" } } : { status: 401, json: { detail: "Not authenticated" } });
      if (path === "/api/reports") return route.fulfill({ json: { reports: [{ analysis_id: 1 }] } });
      if (path === "/api/reports/1") return route.fulfill({ json: { ...report, analysis_id: 1 } });
      if (path.endsWith("/suggestions")) return route.fulfill({ json: suggestions });
      return route.fulfill({ status: 404, json: {} });
    });
    await page.goto("/showcase");
    await page.getByRole("button", { name: "Try Demo" }).click();
    await expect(page).toHaveURL(/\/showcase\/report$/);
    await expect(page.getByRole("heading", { name: "A closer look at workshop attendance" })).toBeVisible();
    await page.getByRole("link", { name: "Compare two columns", exact: true }).click();
    await page.locator("#comparisons summary").first().click();
    await expect(page.locator("#comparisons figure").first()).toBeVisible();
    const firstComparison = page.locator("#comparisons > details").first();
    const technical = firstComparison.locator(".finding-statistics");
    await expect(technical).not.toHaveAttribute("open", "");
    await expect(firstComparison.getByText(/Holm's method/)).not.toBeVisible();
    await technical.getByText("Statistical details", { exact: true }).click();
    await expect(firstComparison.getByText(/Holm's method/)).toBeVisible();
    await technical.getByText("Statistical details", { exact: true }).click();
    await expect(page.locator("#suggestions > article")).toHaveCount(Math.min(3, suggestions.suggestions.filter((s: { finding_type: string }) => !["group_difference", "categorical_association"].includes(s.finding_type)).length));
    await expect(page.locator("#suggestions .finding-chart").first()).not.toHaveAttribute("open", "");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: info.outputPath(`showcase-${width}.png`), fullPage: true });
    await page.reload();
    await expect(page.getByRole("heading", { name: "Read suggestions", exact: true })).toBeVisible();
    signedIn = false;
    await page.reload();
    await expect(page).toHaveURL(/\/showcase$/);
  });
}

test("demo entry failure offers retry and offline sample", async ({ page }) => {
  await page.route("**/api/**", route => route.fulfill({ status: 503, json: { detail: "Demo is being prepared." } }));
  await page.goto("/showcase");
  await page.getByRole("button", { name: "Try Demo" }).click();
  await expect(page.getByRole("alert")).toContainText("Demo is being prepared");
  await expect(page.getByRole("link", { name: "view the offline sample" })).toBeVisible();
});
