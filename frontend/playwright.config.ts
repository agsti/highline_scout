import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "HIGHLINER_DATA_DIR=tests/fixtures/e2e-data uv run uvicorn highliner.server.app:app --host 127.0.0.1 --port 8001",
      url: "http://127.0.0.1:8001/countries",
      cwd: "..",
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "HIGHLINER_API_ORIGIN=http://127.0.0.1:8001 npm run dev -- --port 5174",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
