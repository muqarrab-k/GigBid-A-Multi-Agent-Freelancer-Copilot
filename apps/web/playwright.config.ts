import { defineConfig, devices } from "@playwright/test";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const PORT = 8010;
const venv = resolve("../../.venv/bin/python");
const PYTHON = process.env.PYTHON ?? (existsSync(venv) ? venv : "python");

// api in fake mode serves dist
export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: { baseURL: `http://localhost:${PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `${PYTHON} -m uvicorn apps.api.main:app --port ${PORT}`,
    cwd: "../..",
    env: { GIGBID_FAKE_LLM: "1", HF_HUB_OFFLINE: "1", APP_SECRET_KEY: "e2e-only-secret-key-at-least-32-bytes" },
    url: `http://localhost:${PORT}/health`,
    timeout: 180_000,
    reuseExistingServer: false,
  },
});
