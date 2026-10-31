import { API_BASE, REQUEST_TIMEOUT_MS } from "../config/constants";
import { ApiError, messageFromBody } from "./errors";
import type { Tokens } from "./types";

export interface ClientOptions {
  getTokens: () => Tokens | null;
  /** Called with a fresh pair after a successful refresh. */
  setTokens: (tokens: Tokens) => void;
  /** Called when the session cannot be recovered (refresh failed or no refresh token). */
  onSessionExpired: () => void;
  fetchImpl?: typeof fetch;
  baseUrl?: string;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  query?: Record<string, string | number | undefined>;
  json?: unknown;
  /** application/x-www-form-urlencoded body (the OAuth2 password flow). */
  form?: Record<string, string>;
  signal?: AbortSignal;
  /** Public endpoints (login/register/refresh) neither send nor refresh tokens. */
  anonymous?: boolean;
}

export interface ApiClient {
  request<T>(path: string, options?: RequestOptions): Promise<T>;
  login(email: string, password: string): Promise<Tokens>;
}

const PUBLIC_REFRESH_PATH = "/auth/refresh";

export function createApiClient(options: ClientOptions): ApiClient {
  const doFetch = options.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args));
  const base = options.baseUrl ?? API_BASE;
  let refreshing: Promise<boolean> | null = null;

  function buildUrl(path: string, query?: RequestOptions["query"]): string {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value !== undefined && value !== "") params.set(key, String(value));
    }
    const qs = params.toString();
    return `${base}${path}${qs ? `?${qs}` : ""}`;
  }

  async function send(path: string, opts: RequestOptions, token: string | null): Promise<Response> {
    const headers = new Headers();
    if (token && !opts.anonymous) headers.set("Authorization", `Bearer ${token}`);
    if (opts.json !== undefined) headers.set("Content-Type", "application/json");
    const body = opts.form ? new URLSearchParams(opts.form) : opts.json !== undefined ? JSON.stringify(opts.json) : undefined;

    const timeout = new AbortController();
    const timer = setTimeout(() => timeout.abort(), REQUEST_TIMEOUT_MS);
    opts.signal?.addEventListener("abort", () => timeout.abort(), { once: true });
    try {
      return await doFetch(buildUrl(path, opts.query), {
        method: opts.method ?? "GET",
        headers,
        body,
        signal: timeout.signal,
      });
    } catch (error) {
      if (opts.signal?.aborted) throw error; // the caller cancelled: not a failure to report
      const timedOut = timeout.signal.aborted;
      throw new ApiError(0, timedOut ? "The request timed out." : "Cannot reach the server. Check your connection.");
    } finally {
      clearTimeout(timer);
    }
  }

  async function toError(response: Response): Promise<ApiError> {
    const body: unknown = await response.json().catch(() => null);
    return new ApiError(response.status, messageFromBody(body, response.status), response.headers.get("X-Correlation-ID"));
  }

  /** Single-flight: ten parallel 401s trigger one refresh, not ten. */
  function refreshOnce(): Promise<boolean> {
    refreshing ??= (async () => {
      const current = options.getTokens();
      if (!current?.refresh_token) return false;
      try {
        const response = await send(PUBLIC_REFRESH_PATH, {
          method: "POST",
          json: { refresh_token: current.refresh_token },
          anonymous: true,
        }, null);
        if (!response.ok) return false;
        options.setTokens((await response.json()) as Tokens);
        return true;
      } catch {
        return false;
      } finally {
        refreshing = null;
      }
    })();
    return refreshing;
  }

  async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
    let response = await send(path, opts, options.getTokens()?.access_token ?? null);

    if (response.status === 401 && !opts.anonymous) {
      if (await refreshOnce()) {
        response = await send(path, opts, options.getTokens()?.access_token ?? null);
      }
      if (response.status === 401) {
        options.onSessionExpired();
        throw await toError(response);
      }
    }
    if (!response.ok) throw await toError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  async function login(email: string, password: string): Promise<Tokens> {
    return request<Tokens>("/auth/login", { method: "POST", form: { username: email, password }, anonymous: true });
  }

  return { request, login };
}
