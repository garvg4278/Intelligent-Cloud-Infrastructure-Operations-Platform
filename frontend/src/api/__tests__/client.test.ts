import { describe, expect, it, vi } from "vitest";
import { json } from "../../test/helpers";
import { createApiClient } from "../client";
import { ApiError, messageFromBody } from "../errors";
import type { Tokens } from "../types";

function setup(handler: (url: URL, init: RequestInit) => Response | Promise<Response>, tokens: Tokens | null = { access_token: "old", refresh_token: "r1" }) {
  let current = tokens;
  const calls: { url: URL; init: RequestInit }[] = [];
  const onSessionExpired = vi.fn();
  const client = createApiClient({
    getTokens: () => current,
    setTokens: (t) => { current = t; },
    onSessionExpired,
    fetchImpl: (async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = new URL(String(input), "http://x");
      calls.push({ url, init });
      return handler(url, init);
    }) as typeof fetch,
  });
  return { client, calls, onSessionExpired, tokens: () => current };
}
const auth = (init: RequestInit) => new Headers(init.headers).get("Authorization");

describe("api client", () => {
  it("sends the bearer token and builds the query string, skipping empty values", async () => {
    const { client, calls } = setup(() => json([]));
    await client.request("/incidents", { query: { limit: 5, offset: 0, status_filter: undefined, service_name: "" } });
    expect(calls[0].url.pathname + calls[0].url.search).toBe("/api/v1/incidents?limit=5&offset=0");
    expect(auth(calls[0].init)).toBe("Bearer old");
  });

  it("refreshes once on 401, retries with the new token, and stores the new pair", async () => {
    const { client, calls, tokens, onSessionExpired } = setup((url, init) => {
      if (url.pathname === "/api/v1/auth/refresh") return json({ access_token: "new", refresh_token: "r2" });
      return auth(init) === "Bearer new" ? json({ ok: true }) : json({ detail: "expired" }, 401);
    });
    await expect(client.request("/alerts")).resolves.toEqual({ ok: true });
    expect(tokens()).toEqual({ access_token: "new", refresh_token: "r2" });
    expect(calls.map((c) => c.url.pathname)).toEqual(["/api/v1/alerts", "/api/v1/auth/refresh", "/api/v1/alerts"]);
    expect(onSessionExpired).not.toHaveBeenCalled();
  });

  it("shares one refresh across parallel 401s", async () => {
    const { client, calls } = setup((url, init) => {
      if (url.pathname === "/api/v1/auth/refresh") return json({ access_token: "new", refresh_token: "r2" });
      return auth(init) === "Bearer new" ? json([]) : json({ detail: "expired" }, 401);
    });
    await Promise.all([client.request("/a"), client.request("/b"), client.request("/c")]);
    expect(calls.filter((c) => c.url.pathname.endsWith("/auth/refresh"))).toHaveLength(1);
  });

  it("ends the session when the refresh is rejected", async () => {
    const { client, onSessionExpired } = setup((url) =>
      url.pathname.endsWith("/auth/refresh") ? json({ detail: "Invalid refresh token" }, 401) : json({ detail: "expired" }, 401));
    await expect(client.request("/alerts")).rejects.toMatchObject({ status: 401 });
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
  });

  it("does not try to refresh a failed login (wrong password is not an expired session)", async () => {
    const { client, calls, onSessionExpired } = setup(() => json({ detail: "Incorrect email or password" }, 401), null);
    await expect(client.login("a@b.co", "bad")).rejects.toThrow("Incorrect email or password");
    expect(calls).toHaveLength(1);
    expect(onSessionExpired).not.toHaveBeenCalled();
  });

  it("sends login as a form body with no Authorization header", async () => {
    const { client, calls } = setup(() => json({ access_token: "a", refresh_token: "b" }));
    await client.login("a@b.co", "pw&=x");
    expect(String(calls[0].init.body)).toBe("username=a%40b.co&password=pw%26%3Dx");
    expect(auth(calls[0].init)).toBeNull();
  });

  it("turns network failure and server errors into ApiError with a readable message and correlation id", async () => {
    const down = createApiClient({ getTokens: () => null, setTokens: () => {}, onSessionExpired: () => {}, fetchImpl: (async () => { throw new TypeError("fetch failed"); }) as typeof fetch });
    await expect(down.request("/x")).rejects.toMatchObject({ status: 0, message: expect.stringContaining("Cannot reach the server") });

    const { client } = setup(() => json({ detail: "boom" }, 500, { "X-Correlation-ID": "abc-123" }));
    const error = await client.request("/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 500, requestId: "abc-123", message: "boom" });
  });
});

describe("error messages", () => {
  it("flattens FastAPI validation errors", () => {
    expect(messageFromBody({ detail: [{ loc: ["body", "email"], msg: "value is not a valid email address" }, { msg: "field required" }] }, 422)).toBe("value is not a valid email address; field required");
  });
  it("has sensible fallbacks", () => {
    expect(messageFromBody(null, 429)).toMatch(/Too many requests/);
    expect(messageFromBody({}, 503)).toMatch(/server hit an error/);
    expect(messageFromBody(undefined, 404)).toBe("Request failed (404).");
  });
});
