import { test, expect, type Page } from "@playwright/test";
import { sampleReport } from "../app/lib/sample-report";

const key = "team-science.preferences.v1";
const user = { id: 9, email: "test@example.test" };
const reports = [
  { ...sampleReport, analysis_id: 1, filename: "old.csv", completed_at: "2026-10-01T12:00:00Z", dataset: { rows: 10, columns: 5 }, summary: { ...sampleReport.summary, issues_detected: 9 } },
  { ...sampleReport, analysis_id: 2, filename: "new.csv", completed_at: "2026-10-03T12:00:00Z", dataset: { rows: 100, columns: 5 }, summary: { ...sampleReport.summary, issues_detected: 0 } },
];
async function mockApi(page: Page, signedIn = true) {
  let authenticated = signedIn;
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/login") { authenticated = true; return route.fulfill({ json: user }); }
    if (path === "/api/auth/logout") { authenticated = false; return route.fulfill({ json: {} }); }
    if (!authenticated) return route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
    if (path === "/api/auth/me") return route.fulfill({ json: user });
    if (path === "/api/reports") return route.fulfill({ json: { reports } });
    if (/^\/api\/reports\/\d+$/.test(path)) return route.fulfill({ json: { ...sampleReport, analysis_id: Number(path.split("/").at(-1)) } });
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
}

test("public homepage stays general and Sign in reopens an existing product session", async ({ page }) => {
  await mockApi(page, false);
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Email", { exact: true }).fill(user.email);
  await page.getByLabel("Password", { exact: true }).fill("test-only-password");
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.locator(".desktop-sidebar").getByRole("link", { name: "Home", exact: true })).toHaveCount(0);
  await page.goto("/");
  await expect(page.getByRole("link", { name: "My account" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Log out", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Sign in", exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByLabel("Password", { exact: true })).toHaveCount(0);
  await page.goto("/login?next=/reports");
  await expect(page).toHaveURL(/\/reports$/);
  await page.locator(".desktop-sidebar").getByRole("button", { name: "Log out", exact: true }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5186/");
  await expect(page.getByRole("link", { name: "Sign in", exact: true })).toBeVisible();
});

test("sidebar collapse persists, resizes content, and preserves accessible account navigation", async ({ page }) => {
  await mockApi(page); await page.goto("/dashboard");
  const before = await page.locator(".workspace").boundingBox();
  await page.getByRole("button", { name: "Collapse sidebar", exact: true }).click();
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute("aria-expanded", "false");
  await expect.poll(async () => (await page.locator(".workspace").boundingBox())!.width).toBeGreaterThan(before!.width);
  await page.reload();
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
  await page.locator(".desktop-sidebar").getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
  await page.screenshot({ path: "../.run/settings-collapsed.png", fullPage: true });
});

test("mobile drawer traps focus, closes with Escape, and closes after navigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 }); await mockApi(page); await page.goto("/dashboard");
  const menu = page.getByRole("button", { name: "Open navigation" });
  await menu.click();
  const drawer = page.getByRole("dialog", { name: "Application navigation" });
  await expect(drawer).toBeVisible();
  await expect(menu).toHaveAttribute("aria-expanded", "true");
  await page.screenshot({ path: "../.run/mobile-navigation.png", fullPage: true });
  for (let i = 0; i < 16; i++) await page.keyboard.press("Tab");
  expect(await drawer.evaluate(element => element.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(drawer).not.toBeVisible(); await expect(menu).toBeFocused();
  await menu.click(); await drawer.getByRole("link", { name: "Saved Reports", exact: true }).click();
  await expect(page).toHaveURL(/\/reports$/); await expect(drawer).not.toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("theme is consistent across all routes, persists, and follows system changes", async ({ page }) => {
  await mockApi(page); await page.emulateMedia({ colorScheme: "light" }); await page.goto("/settings");
  await page.getByRole("radio", { name: /Dark mode/ }).check();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({ path: "../.run/settings-dark.png", fullPage: true });
  const background = await page.locator("body").evaluate(element => getComputedStyle(element).backgroundColor);
  for (const path of ["/dashboard", "/", "/upload", "/reports", "/reports/1", "/reports/1?view=columns", "/login", "/register"]) {
    await page.goto(path); await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    expect(await page.locator("body").evaluate(element => getComputedStyle(element).backgroundColor)).toBe(background);
  }
  await page.goto("/settings"); await page.getByRole("radio", { name: /System default/ }).check();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.emulateMedia({ colorScheme: "dark" }); await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("radio", { name: /Light mode/ }).check();
  await page.reload(); await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("density, motion, default sorting, per-view sorting and confirmed reset work", async ({ page }) => {
  await mockApi(page); await page.goto("/settings");
  await page.getByLabel("Interface density").selectOption("compact");
  await page.getByLabel("Animations", { exact: true }).selectOption("reduce");
  await page.getByLabel("Default report sorting").selectOption("most-issues");
  await expect(page.locator("html")).toHaveAttribute("data-density", "compact");
  await expect(page.locator("html")).toHaveAttribute("data-motion", "reduce");
  await page.goto("/reports");
  await expect(page.locator(".report-list-item").first()).toContainText("old.csv");
  await page.getByRole("combobox", { name: "Sort reports", exact: true }).selectOption("fewest-issues");
  await expect(page.locator(".report-list-item").first()).toContainText("new.csv");
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)!).reportSort, key)).toBe("most-issues");
  await page.getByLabel("Search reports").fill("old"); await expect(page.locator(".report-list-item")).toHaveCount(1);
  await page.goto("/settings"); await page.getByRole("button", { name: "Reset to Defaults" }).click();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByLabel("Interface density")).toHaveValue("compact");
  await page.getByRole("button", { name: "Reset to Defaults" }).click();
  await page.getByRole("button", { name: "Reset preferences", exact: true }).click();
  await expect(page.getByLabel("Interface density")).toHaveValue("comfortable");
  await expect(page.getByLabel("Default report sorting")).toHaveValue("newest");
  await expect(page.getByText(user.email, { exact: true }).last()).toBeVisible();
});

test("unauthenticated settings redirect and invalid stored preferences fall back safely", async ({ page }) => {
  await mockApi(page, false);
  await page.addInitScript(key => localStorage.setItem(key, '{"theme":"unknown","reportSort":"__proto__","sidebarCollapsed":"yes"}'), key);
  await page.goto("/settings"); await expect(page).toHaveURL(/\/login\?next=\/settings$/);
  await expect(page.locator("html")).toHaveAttribute("data-density", "comfortable");
});

test("preferences synchronize across tabs and blocked storage does not break settings", async ({ page, context }) => {
  await mockApi(page); await page.goto("/settings");
  const second = await context.newPage(); await mockApi(second); await second.goto("/dashboard");
  await page.getByRole("radio", { name: /Dark mode/ }).check();
  await expect(second.locator("html")).toHaveAttribute("data-theme", "dark");
  await second.close();
  await page.addInitScript(() => Object.defineProperty(window, "localStorage", { get() { throw Error("Storage blocked"); } }));
  await page.reload(); await page.getByRole("radio", { name: /Light mode/ }).check();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("temporary account failures retain the signed-in user and settings can retry", async ({ page }) => {
  await mockApi(page); await page.goto("/dashboard");
  await expect(page.locator(".desktop-sidebar .sidebar-user")).toBeVisible();
  await page.route("**/api/auth/me", route => route.fulfill({ status: 503, json: { detail: "Temporarily unavailable" } }));
  await page.locator(".desktop-sidebar").getByRole("link", { name: "Documentation", exact: true }).click();
  await expect(page.locator(".desktop-sidebar .sidebar-user")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry account" })).toBeVisible();
  await page.goto("/settings"); await expect(page.getByRole("heading", { name: "Unable to load settings" })).toBeVisible();
  await page.unroute("**/api/auth/me");
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
});

test("five minutes without interaction expires the product session without background renewal", async ({ page }) => {
  await page.clock.install();
  await mockApi(page);
  let checks = 0;
  page.on("request", request => { if (new URL(request.url()).pathname === "/api/auth/me") checks++; });
  await page.goto("/dashboard");
  await expect(page.locator(".desktop-sidebar .sidebar-user")).toBeVisible();
  const initialChecks = checks;
  await page.clock.fastForward(299_000);
  await expect(page).toHaveURL(/\/dashboard$/);
  expect(checks).toBe(initialChecks);
  await page.clock.fastForward(1_001);
  await expect(page).toHaveURL(/\/login\?next=%2Fdashboard$/);
  await expect(page.getByLabel("Password", { exact: true })).toBeVisible();
});

test("real interaction renews activity but does not prevent a later idle expiry", async ({ page }) => {
  await page.clock.install(); await mockApi(page); await page.goto("/dashboard");
  await expect(page.locator(".desktop-sidebar .sidebar-user")).toBeVisible();
  await page.clock.fastForward(240_000);
  const renewed = page.waitForResponse(response => new URL(response.url()).pathname === "/api/auth/me");
  await page.keyboard.press("Tab"); await renewed;
  await page.clock.fastForward(240_000);
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.clock.fastForward(60_001);
  await expect(page).toHaveURL(/\/login\?next=%2Fdashboard$/);
});

test("appearance accent colors apply across themes and routes, persist, and restore", async ({ page, context }) => {
  await mockApi(page); await page.goto("/settings");
  await page.getByRole("radio", { name: /Light mode/ }).check();
  await page.getByRole("radio", { name: "Teal", exact: true }).check();
  await expect(page.locator("html")).toHaveAttribute("data-accent", "teal");
  await page.reload();
  await expect(page.getByRole("radio", { name: "Teal", exact: true })).toBeChecked();
  await page.goto("/dashboard");
  await expect(page.getByRole("link", { name: "Analyze Dataset", exact: true })).toHaveCSS("background-color", "rgb(15, 118, 110)");
  await page.goto("/settings");
  await page.getByRole("radio", { name: /Dark mode/ }).check();
  await expect(page.locator("html")).toHaveAttribute("data-accent", "teal");
  await page.goto("/dashboard");
  await expect(page.getByRole("link", { name: "Analyze Dataset", exact: true })).toHaveCSS("background-color", "rgb(110, 218, 204)");
  const second = await context.newPage(); await mockApi(second); await second.goto("/settings");
  await second.getByRole("radio", { name: "Rose", exact: true }).check();
  await expect(page.locator("html")).toHaveAttribute("data-accent", "rose");
  await second.getByRole("button", { name: "Restore default color", exact: true }).click();
  await expect(second.getByRole("radio", { name: "Violet", exact: true })).toBeChecked();
  await expect(page.locator("html")).toHaveAttribute("data-accent", "violet");
  await second.close();
});
