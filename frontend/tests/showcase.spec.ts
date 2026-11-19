import { test, expect } from "@playwright/test";

for (const width of [320, 375, 390, 768, 1440]) {
  test(`verification gate and mobile layout at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    let verified = false;
    await page.route("**/api/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/register" || path === "/api/auth/resend-verification") return route.fulfill({ json: { verification_required: true } });
      if (path === "/api/auth/verify-email") {
        if (route.request().postDataJSON().code !== "12345678") return route.fulfill({ status: 400, json: { detail: "Invalid or expired code." } });
        verified = true;
        return route.fulfill({ json: { id: 1, email: "verified@example.com" } });
      }
      if (path === "/api/auth/me") return route.fulfill(verified ? { json: { id: 1, email: "verified@example.com" } } : { status: 401, json: { detail: "Not authenticated" } });
      if (path === "/api/reports") return route.fulfill({ json: { reports: [] } });
      return route.fulfill({ status: 404, json: {} });
    });
    for (const path of ["/", "/showcase", "/showcase/report", "/example-report", "/documentation", "/reports/1"]) {
      await page.goto(path);
      await expect(page).toHaveURL(/\/login\?next=/);
      await expect(page.getByRole("heading", { name: "Log in", exact: true })).toBeVisible();
      await expect(page.getByRole("complementary", { name: "Application navigation" })).toHaveCount(0);
    }
    await page.getByRole("link", { name: "Create an account" }).click();
    await expect(page.getByRole("heading", { name: "Register", exact: true })).toBeVisible();
    await page.getByLabel("Email", { exact: true }).fill("verified@example.com");
    await page.getByLabel("Password", { exact: true }).fill("a-long-test-password");
    await page.getByLabel("Confirm password", { exact: true }).fill("a-long-test-password");
    await page.getByRole("button", { name: "Create account", exact: true }).click();
    await expect(page).toHaveURL(/\/verify-email$/);
    await expect(page.getByRole("heading", { name: "Verify your email" })).toBeVisible();
    await page.getByLabel("Verification code").fill("00000000");
    await page.getByRole("button", { name: "Verify email", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("Invalid or expired");
    await page.getByRole("button", { name: "Resend code" }).click();
    await expect(page.getByRole("status")).toContainText("A new code has been sent");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`verification-${width}.png`), fullPage: true });
    await page.getByLabel("Verification code").fill("12345678");
    await page.getByRole("button", { name: "Verify email", exact: true }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByRole("heading", { name: "Good data. Better questions.", exact: true })).toBeVisible();
  });
}

test("email delivery failure stays outside the app and supports retry", async ({ page }) => {
  await page.route("**/api/**", route => {
    if (route.request().url().endsWith("/me")) return route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
    return route.fulfill({ status: 503, json: { detail: "Verification email could not be sent." } });
  });
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill("verified@example.com");
  await page.getByLabel("Password", { exact: true }).fill("a-long-test-password");
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(page).toHaveURL(/\/verify-email\?delivery=failed/);
  await expect(page.getByRole("alert")).toContainText("couldn't send");
  await expect(page.getByRole("button", { name: "Resend code" })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Application navigation" })).toHaveCount(0);
});
