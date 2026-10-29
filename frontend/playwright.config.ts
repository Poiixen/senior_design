import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests", fullyParallel: false, workers: 1,
  timeout: 30_000, reporter: "list", outputDir: "../.run/playwright-results",
  use: { baseURL: "http://127.0.0.1:5186", channel: process.env.PLAYWRIGHT_CHANNEL || "chrome", headless: true, viewport: { width: 1440, height: 1000 }, screenshot: "only-on-failure", trace: "retain-on-failure" },
  webServer: { command: "node node_modules/@react-router/serve/bin.cjs ./build/server/index.js", url: "http://127.0.0.1:5186", reuseExistingServer: false, env: { PORT: "5186", HOST: "127.0.0.1" }, timeout: 60_000 },
});
