/** Single place for values that were string literals scattered through the UI. */
export const APP_NAME = "ICOP";
export const API_BASE = "/api/v1";
export const REQUEST_TIMEOUT_MS = 15_000;
export const PAGE_SIZE = 25;

/** Services the analytics overview can be scoped to. */
export const SERVICE_OPTIONS = [
  "gateway",
  "auth",
  "deployment",
  "alert",
  "incident",
  "aiops",
  "analytics",
  "notification",
  "audit",
  "infrastructure",
] as const;

export const STORAGE_KEYS = {
  session: "icop.session",
  theme: "icop.theme",
} as const;
