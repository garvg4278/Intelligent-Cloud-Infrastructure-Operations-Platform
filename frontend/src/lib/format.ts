const EMPTY = "—";

export function formatNumber(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? new Intl.NumberFormat().format(value) : EMPTY;
}

/** The API reports rates as fractions (0.9167); people read percentages. */
export function formatPercent(fraction: unknown): string {
  if (typeof fraction !== "number" || !Number.isFinite(fraction)) return EMPTY;
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(fraction * 100)}%`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return EMPTY;
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? EMPTY
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function formatDuration(seconds: unknown): string {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) return EMPTY;
  if (seconds < 90) return `${Math.round(seconds)}s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min`;
  if (seconds < 172800) return `${(seconds / 3600).toFixed(1)} h`;
  return `${(seconds / 86400).toFixed(1)} d`;
}

/** "in_progress" -> "in progress" */
export function humanize(value: string): string {
  return value.replace(/_/g, " ");
}
