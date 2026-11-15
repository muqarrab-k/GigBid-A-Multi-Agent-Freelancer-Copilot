import { expect, test } from "@playwright/test";
import { newUser, signIn } from "./helpers";

test("marketplace outage shows the banner, recovery hides it", async ({ page, request }) => {
  const { token } = await newUser(request);
  await signIn(page, token);
  await page.goto("/jobs");
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
  await expect(page.getByText("Marketplace unavailable")).toHaveCount(0);
  try {
    await request.post("/test/marketplace", { data: { down: true } });
    await page.reload();
    await expect(page.getByRole("alert").filter({ hasText: "Marketplace unavailable" })).toBeVisible();
  } finally {
    await request.post("/test/marketplace", { data: { down: false } });
  }
  await page.reload();
  await expect(page.getByText("Marketplace unavailable")).toHaveCount(0);
});
