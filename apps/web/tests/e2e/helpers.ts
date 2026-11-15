import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const JOB = "1c0b990bb7dbe947";
const PERSONA_PASSWORD = "e2e-password-123";

let counter = 0;

// fresh user per test
export async function newUser(request: APIRequestContext, persona = "ai_ml"): Promise<{ username: string; token: string }> {
  counter += 1;
  const username = `e2e${Date.now() % 100000}${counter}`;
  const reg = await request.post("/auth/register", { data: { username, password: PERSONA_PASSWORD, persona } });
  expect(reg.status()).toBe(201);
  const login = await request.post("/auth/login", { data: { username, password: PERSONA_PASSWORD } });
  return { username, token: (await login.json()).access_token };
}

export async function signIn(page: Page, token: string): Promise<void> {
  await page.addInitScript((t) => localStorage.setItem("gigbid.token", t), token);
}

// run until approval
export async function pendingDraft(request: APIRequestContext, token: string): Promise<string> {
  const headers = { Authorization: `Bearer ${token}` };
  const run = await request.post("/runs", { headers, data: { job_id: JOB } });
  expect(run.status()).toBe(202);
  const threadId = (await run.json()).thread_id as string;
  await expect.poll(async () => {
    const res = await request.get("/approvals", { headers });
    return (await res.json()).items.some((i: { thread_id: string }) => i.thread_id === threadId);
  }, { timeout: 30_000 }).toBe(true);
  return threadId;
}

export const studio = (threadId: string) => `/approvals/${encodeURIComponent(threadId)}`;
