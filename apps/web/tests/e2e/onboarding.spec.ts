import { expect, test } from "@playwright/test";

test("sign up, pick a persona, set budget and upload a case study", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "New here? Create an account" }).click();
  await page.getByLabel("Username").fill(`onboard${Date.now() % 100000}`);
  await page.getByLabel("Password").fill("onboarding-pass-1");
  await page.getByLabel("Data analyst").check();
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page).toHaveURL(/\/onboarding$/);
  await expect(page.getByText("data_analyst")).toBeVisible();
  await expect(page.getByText("Upwork")).toBeVisible();
  await expect(page.getByText("not connected")).toBeVisible();

  await page.getByLabel("Weekly Connects budget").fill("60");
  await page.getByLabel("Add a saved search (keywords)").fill("power bi dashboard");
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(page.getByText("Saved.")).toBeVisible();

  await page.getByLabel("Upload a case study (.md or .txt)").setInputFiles({
    name: "retail-dashboard.md", mimeType: "text/markdown",
    buffer: Buffer.from("# Retail dashboard\n\nBuilt a Power BI sales dashboard for a retail chain with daily refresh."),
  });
  await page.getByRole("button", { name: "Upload and index" }).click();
  await expect(page.getByText(/Indexed data_analyst:upload:retail-dashboard-md/)).toBeVisible();

  await page.getByRole("button", { name: "Go to my inbox" }).click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
  await page.goto("/settings");
  await expect(page.getByLabel("Weekly Connects budget")).toHaveValue("60");
});
