import { humanize } from "../lib/format";

type Tone = "good" | "bad" | "warn" | "info" | "neutral";

/**
 * Every status/severity value the API can emit, mapped to a tone. (The old UI
 * styled `active`/`provisioned`, values the API never sends, so a real
 * environment in `ready` rendered unstyled.)
 */
const TONES: Record<string, Tone> = {
  ready: "good", resolved: "good", closed: "neutral", succeeded: "good",
  open: "bad", firing: "bad", provision_failed: "bad", destroy_failed: "bad", critical: "bad", failed: "bad",
  acknowledged: "warn", investigating: "warn", mitigated: "info", high: "warn", medium: "warn",
  pending: "info", provisioning_infra: "info", configuring_nodes: "info", destroying: "info", low: "info",
  destroyed: "neutral",
};

export function StatusBadge({ value }: { value: string }) {
  return <span className={`badge badge-${TONES[value] ?? "neutral"}`}>{humanize(value)}</span>;
}
