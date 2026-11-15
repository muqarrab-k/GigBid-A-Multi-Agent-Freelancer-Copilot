import base from "./playwright.config";
import { defineConfig } from "@playwright/test";

// readme gif: approve test, slowed down, recorded
export default defineConfig({
  ...base,
  reporter: [["list"]],
  outputDir: "test-results/demo",
  use: {
    ...base.use,
    video: { mode: "on", size: { width: 1280, height: 800 } },
    viewport: { width: 1280, height: 800 },
    launchOptions: { slowMo: 350 },
  },
});
