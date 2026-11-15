import { expect, test } from "@playwright/test";
import { JOB, newUser, pendingDraft, signIn, studio } from "./helpers";

const SHOTS = "../../docs/images";

test("inbox, run viewer and studio; approve submits once and survives a refresh", async ({ page, request }) => {
  const { token } = await newUser(request);
  await signIn(page, token);

  await page.goto("/jobs");
  await page.getByRole("button", { name: "Run scout" }).click();
  await expect(page.getByText(/new jobs found/)).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/ui_inbox.png`, fullPage: false });

  await page.goto(`/jobs/${JOB}`);
  await page.getByRole("button", { name: "Start bid run" }).click();
  await expect(page.getByRole("heading", { name: "Agent run" })).toBeVisible();
  await expect(page.getByText("waiting for you")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("trace-id")).not.toHaveText("…");
  await page.screenshot({ path: `${SHOTS}/ui_run_viewer.png`, fullPage: true });

  await page.getByRole("link", { name: "Review the proposal" }).click();
  await expect(page.getByRole("heading", { name: "Proposal studio" })).toBeVisible();
  // a refresh still shows it
  await page.reload();
  await expect(page.getByText("What will be sent")).toBeVisible();
  await expect(page.getByTestId("balance-after")).not.toHaveText("—");
  const claim = page.getByTestId("letter").getByRole("button").first();
  await claim.focus();
  await expect(page.getByRole("tooltip").first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/ui_studio.png`, fullPage: true });
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip").first()).toBeHidden();

  await page.getByRole("button", { name: "Approve and send" }).click();
  await expect(page.getByText("Status submitted")).toBeVisible();

  const headers = { Authorization: `Bearer ${token}` };
  const proposals = await (await request.get("/proposals", { headers })).json();
  expect(proposals.items.filter((p: { job_id: string }) => p.job_id === JOB)).toHaveLength(1);
  await page.goto("/pipeline");
  await expect(page.getByRole("region", { name: "submitted" }).getByText(JOB)).toBeVisible();
});

test("reject with a reason records it", async ({ page, request }) => {
  const { token } = await newUser(request, "fullstack");
  const threadId = await pendingDraft(request, token);
  await signIn(page, token);
  await page.goto(studio(threadId));
  await page.getByRole("button", { name: "Reject" }).click();
  await expect(page.getByRole("button", { name: "Confirm reject" })).toBeDisabled();
  await page.getByLabel("Reason").fill("budget too low for the scope");
  await page.getByRole("button", { name: "Confirm reject" }).click();
  await expect(page.getByText("Status rejected")).toBeVisible();
  await expect(page.getByText(/budget too low for the scope/)).toBeVisible();
  await page.goto("/analytics");
  await expect(page.getByText("human: budget too low for the scope")).toBeVisible();
});

test("editing a draft reruns the checks", async ({ page, request }) => {
  // edits never submit
  const { token } = await newUser(request, "fullstack");
  const threadId = await pendingDraft(request, token);
  await signIn(page, token);
  await page.goto(studio(threadId));
  await page.getByRole("button", { name: "Edit" }).click();
  const box = page.getByLabel("Edited text");
  await box.fill(`${await box.inputValue()}\n\nReach me at sam@example.com for faster replies.`);
  await page.getByRole("button", { name: "Save edit and recheck" }).click();
  // compliance blocks the contact detail
  await expect(page.getByText("Status blocked")).toBeVisible();
  await expect(page.getByText(/no_contact_details/)).toBeVisible();
});
