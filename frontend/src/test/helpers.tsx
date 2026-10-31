import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { Providers } from "../app/Providers";
import type { Role } from "../api/types";
import { DEFAULT_CONFIG, type RuntimeConfig } from "../config/runtime";
import { STORAGE_KEYS } from "../config/constants";

const b64url = (value: object) => btoa(JSON.stringify(value)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");

/** An unsigned token with the claims the UI reads. The signature is never checked client-side. */
export function fakeToken(role: Role, expiresInSeconds = 600, sub = "user@example.com"): string {
  return `${b64url({ alg: "HS256", typ: "JWT" })}.${b64url({ sub, role, exp: Math.floor(Date.now() / 1000) + expiresInSeconds })}.sig`;
}

export function seedSession(role: Role, email = "user@example.com") {
  window.localStorage.setItem(
    STORAGE_KEYS.session,
    JSON.stringify({ access_token: fakeToken(role, 600, email), refresh_token: "refresh-1", email }),
  );
}

export const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

export type Route = (url: URL, init: RequestInit) => Response | Promise<Response> | undefined;

/** A fetch double driven by a list of route handlers; unmatched requests fail the test loudly. */
export function mockFetch(...routes: Route[]) {
  const calls: { url: URL; init: RequestInit }[] = [];
  const impl = (async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://localhost");
    calls.push({ url, init });
    for (const route of routes) {
      const result = route(url, init);
      if (result) return result;
    }
    throw new Error(`Unmocked request: ${init.method ?? "GET"} ${url.pathname}${url.search}`);
  }) as typeof fetch;
  return { fetch: impl, calls };
}

export const on = (method: string, path: string, respond: (url: URL, init: RequestInit) => Response): Route =>
  (url, init) => ((init.method ?? "GET") === method && url.pathname === path ? respond(url, init) : undefined);

export function renderApp(ui: ReactElement, options: { fetch?: typeof fetch; config?: Partial<RuntimeConfig> } = {}) {
  return render(
    <Providers config={{ ...DEFAULT_CONFIG, ...options.config }} fetchImpl={options.fetch}>
      {ui}
    </Providers>,
  );
}

/** Routes every read endpoint the console calls with empty-but-valid data. */
export const emptyApi: Route[] = [
  on("GET", "/api/v1/analytics/overview", () => json({ service_name: "gateway", deployments: { total: 0, success_rate: null, deployments_per_day: null }, incidents: { total: 0, by_status: {}, avg_resolution_seconds: null }, alerts: { total: 0, by_status: {} } })),
  on("GET", "/api/v1/incidents", () => json([])),
  on("GET", "/api/v1/alerts", () => json([])),
  on("GET", "/api/v1/infrastructure/environments", () => json([])),
  on("GET", "/api/v1/audit/events", () => json([])),
  on("GET", "/api/v1/auth/users", () => json([])),
];
