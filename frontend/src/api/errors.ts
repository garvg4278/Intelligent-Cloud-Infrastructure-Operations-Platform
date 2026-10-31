/** Every failed request, whatever the cause, surfaces as one of these. */
export class ApiError extends Error {
  readonly status: number;
  /** The gateway's X-Correlation-ID, so a user can quote it to whoever runs the platform. */
  readonly requestId: string | null;

  constructor(status: number, message: string, requestId: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }
  get isForbidden(): boolean {
    return this.status === 403;
  }
}

/** FastAPI sends `detail` as a string, or a list of {loc,msg} for validation errors. */
export function messageFromBody(body: unknown, status: number): string {
  const detail = typeof body === "object" && body !== null ? (body as { detail?: unknown }).detail : undefined;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => (typeof item === "object" && item !== null ? (item as { msg?: unknown }).msg : null))
      .filter((msg): msg is string => typeof msg === "string");
    if (parts.length) return parts.join("; ");
  }
  if (status === 429) return "Too many requests. Wait a moment and try again.";
  if (status >= 500) return "The server hit an error. Try again shortly.";
  return `Request failed (${status}).`;
}

export function describeError(error: unknown, fallback = "Something went wrong."): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
