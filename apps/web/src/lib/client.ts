import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./api/schema";

export type Schemas = components["schemas"];

const KEY = "gigbid.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(KEY, token);
    else localStorage.removeItem(KEY);
  } catch {
    // private mode
  }
}

const auth: Middleware = {
  onRequest({ request }) {
    const token = getToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    request.headers.set("Accept", "application/json");
    // never reuse a cached page
    return new Request(request, { cache: "no-store" });
  },
  onResponse({ response }) {
    if (response.status === 401 && !location.pathname.startsWith("/login")) {
      setToken(null);
      location.assign("/login");
    }
    return response;
  },
};

export const api = createClient<paths>({ baseUrl: "" });
api.use(auth);

// throw on api errors
export async function must<T>(call: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await call;
  if (error !== undefined || data === undefined) {
    const detail = (error as { detail?: unknown } | undefined)?.detail;
    throw new Error(typeof detail === "string" ? detail : `request failed (${response.status})`);
  }
  return data;
}
