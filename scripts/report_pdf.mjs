// docs/report/REPORT.md -> REPORT.pdf: pandoc html, chromium print
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const report = resolve(root, "docs/report");
const html = resolve(report, "REPORT.html");
const require = createRequire(resolve(root, "apps/web/package.json"));
const { chromium } = require("@playwright/test");

execFileSync("pandoc", ["REPORT.md", "-s", "--embed-resources", "--css", "report.css", "-o", html], { cwd: report });
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(`file://${html}`);
await page.pdf({
  path: resolve(report, "REPORT.pdf"),
  // page size, margins and page numbers come from report.css
  preferCSSPageSize: true,
  printBackground: true,
});
await browser.close();
console.log("wrote docs/report/REPORT.pdf");
