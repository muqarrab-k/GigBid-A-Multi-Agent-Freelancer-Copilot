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
  format: "A4",
  printBackground: true,
  displayHeaderFooter: true,
  headerTemplate: "<span></span>",
  footerTemplate: '<div style="font-size:7pt;width:100%;text-align:center;color:#666"><span class="pageNumber"></span> / <span class="totalPages"></span></div>',
  margin: { top: "16mm", bottom: "16mm", left: "15mm", right: "15mm" },
});
await browser.close();
console.log("wrote docs/report/REPORT.pdf");
