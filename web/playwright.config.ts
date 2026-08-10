import { defineConfig, devices } from "@playwright/test";

const BASE_URL =
  process.env.WEB_BASE_URL ||
  "http://127.0.0.1:3782";
const SERIAL_MODE = process.env.PW_SERIAL === "1";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: !SERIAL_MODE,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: SERIAL_MODE ? 1 : undefined,
  reporter: [["html", { open: "never" }], ["list"]],
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3782",
    url: "http://127.0.0.1:3782/education",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "ui-audit",
      testMatch: "**/*.audit.ts",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "e2e",
      testMatch: "**/*.spec.ts",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
