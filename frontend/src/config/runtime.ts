/**
 * Runtime configuration.
 *
 * Environment-specific values (where Grafana lives, who to contact) must not be
 * compiled into the bundle, or every environment needs its own image. They are
 * served as /config.json instead: in Docker the nginx entrypoint generates that
 * file from environment variables (see docker/40-icop-config.sh); in `vite dev`
 * the committed public/config.json is used.
 *
 * Everything in here is validated. A malformed or hostile config.json (for
 * example a `javascript:` URL that would become an <a href>) falls back to
 * "feature off" rather than being rendered.
 */

export interface RuntimeConfig {
  /** Shown in the header badge, e.g. "staging". Null hides the badge. */
  environmentLabel: string | null;
  /** Link target for the Grafana nav item. Null hides the item. */
  grafanaUrl: string | null;
  /** Link target for the API documentation nav item. Null hides the item. */
  apiDocsUrl: string | null;
  /** Shown (clickable + copyable) in the footer. Null hides it. */
  supportEmail: string | null;
}

export const DEFAULT_CONFIG: RuntimeConfig = {
  environmentLabel: null,
  grafanaUrl: null,
  apiDocsUrl: null,
  supportEmail: null,
};

const EMAIL_PATTERN = /^[^\s@<>"']+@[^\s@<>"']+\.[^\s@<>"']+$/;
const LABEL_PATTERN = /^[\w .-]{1,32}$/;

/** Accept only absolute http(s) URLs; anything else is treated as unset. */
export function safeHttpUrl(value: unknown): string | null {
  if (typeof value !== "string" || value.trim() === "") return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export function parseConfig(raw: unknown): RuntimeConfig {
  if (typeof raw !== "object" || raw === null) return { ...DEFAULT_CONFIG };
  const source = raw as Record<string, unknown>;
  const email = typeof source.supportEmail === "string" ? source.supportEmail.trim() : "";
  const label = typeof source.environmentLabel === "string" ? source.environmentLabel.trim() : "";
  return {
    environmentLabel: LABEL_PATTERN.test(label) ? label : null,
    grafanaUrl: safeHttpUrl(source.grafanaUrl),
    apiDocsUrl: safeHttpUrl(source.apiDocsUrl),
    supportEmail: EMAIL_PATTERN.test(email) ? email : null,
  };
}

export async function loadConfig(fetchImpl: typeof fetch = fetch): Promise<RuntimeConfig> {
  try {
    const response = await fetchImpl("/config.json", { cache: "no-store" });
    if (!response.ok) return { ...DEFAULT_CONFIG };
    return parseConfig(await response.json());
  } catch {
    return { ...DEFAULT_CONFIG };
  }
}
