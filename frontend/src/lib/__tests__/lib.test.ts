import { describe, expect, it } from "vitest";
import { DEFAULT_CONFIG, parseConfig, safeHttpUrl } from "../../config/runtime";
import { fakeToken } from "../../test/helpers";
import { matchesQuery } from "../filter";
import { formatDuration, formatNumber, formatPercent, humanize } from "../format";
import { ALLOWED_TRANSITIONS } from "../incidents";
import { decodeClaims, hasRole } from "../jwt";
import { summarizeOverview } from "../overview";

describe("runtime config", () => {
  it("accepts only http(s) URLs, so a hostile config.json cannot inject a javascript: link", () => {
    expect(safeHttpUrl("javascript:alert(1)")).toBeNull();
    expect(safeHttpUrl("data:text/html,<script>")).toBeNull();
    expect(safeHttpUrl("/relative")).toBeNull();
    expect(safeHttpUrl("")).toBeNull();
    expect(safeHttpUrl("https://grafana.example.com/d/x")).toBe("https://grafana.example.com/d/x");
  });

  it("falls back to everything-off for junk and keeps only valid fields", () => {
    expect(parseConfig(null)).toEqual(DEFAULT_CONFIG);
    expect(parseConfig("nope")).toEqual(DEFAULT_CONFIG);
    const parsed = parseConfig({ grafanaUrl: "javascript:1", apiDocsUrl: "http://a.test/docs", supportEmail: "not an email", environmentLabel: "<img onerror=x>" });
    expect(parsed).toEqual({ grafanaUrl: null, apiDocsUrl: "http://a.test/docs", supportEmail: null, environmentLabel: null });
    expect(parseConfig({ supportEmail: "ops@example.com", environmentLabel: "staging" })).toMatchObject({ supportEmail: "ops@example.com", environmentLabel: "staging" });
  });
});

describe("jwt claims (UI hint only)", () => {
  it("reads sub/role/exp", () => {
    expect(decodeClaims(fakeToken("operator", 60, "a@b.co"))).toMatchObject({ sub: "a@b.co", role: "operator" });
  });
  it("rejects garbage, missing claims and unknown roles", () => {
    expect(decodeClaims("not-a-token")).toBeNull();
    expect(decodeClaims("a.b.c")).toBeNull();
    const evil = `x.${btoa(JSON.stringify({ sub: "a", exp: 1, role: "root" }))}.y`;
    expect(decodeClaims(evil)).toBeNull();
  });
  it("orders roles viewer < developer < operator < admin", () => {
    expect(hasRole("operator", "viewer")).toBe(true);
    expect(hasRole("developer", "operator")).toBe(false);
    expect(hasRole(null, "viewer")).toBe(false);
  });
});

describe("formatting", () => {
  it("shows rates as percentages (the API sends fractions)", () => {
    expect(formatPercent(0.9167)).toMatch(/91\.7%/);
    expect(formatPercent(null)).toBe("—");
  });
  it("handles missing values without printing 'undefined' or 'NaN'", () => {
    expect(formatNumber(undefined)).toBe("—");
    expect(formatNumber(NaN)).toBe("—");
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(45)).toBe("45s");
    expect(formatDuration(3600)).toBe("60 min");
    expect(humanize("provisioning_infra")).toBe("provisioning infra");
  });
  it("filters case-insensitively across fields and ignores blanks", () => {
    expect(matchesQuery("GATE", "gateway", null)).toBe(true);
    expect(matchesQuery("zzz", "gateway", undefined)).toBe(false);
    expect(matchesQuery("  ", "anything")).toBe(true);
  });
});

describe("overview summary", () => {
  it("derives open incidents and firing alerts from by_status (the API has no open_count/active_count)", () => {
    const cards = summarizeOverview({
      service_name: "gateway",
      deployments: { total: 12, success_rate: 0.75, deployments_per_day: 1.5 },
      incidents: { total: 7, by_status: { open: 2, investigating: 1, resolved: 3, closed: 1 }, avg_resolution_seconds: 600 },
      alerts: { total: 9, by_status: { firing: 4, resolved: 5 } },
    });
    const byId = Object.fromEntries(cards.map((c) => [c.id, c]));
    expect(byId["open-incidents"].value).toBe("3");
    expect(byId["firing-alerts"].value).toBe("4");
    expect(byId["success"].value).toMatch(/75%/);
  });
  it("marks a failed section as degraded instead of showing a misleading zero", () => {
    const cards = summarizeOverview({ service_name: "x", deployments: { error: "deployment service unavailable" }, incidents: { total: 0, by_status: {}, avg_resolution_seconds: null }, alerts: { total: 0, by_status: {} } });
    expect(cards.find((c) => c.id === "success")).toMatchObject({ value: "—", degraded: "deployment service unavailable" });
    expect(cards.find((c) => c.id === "open-incidents")?.value).toBe("0");
  });
  it("renders placeholders, not crashes, before data arrives", () => {
    expect(summarizeOverview(null)).toHaveLength(4);
  });
});

describe("incident transitions", () => {
  it("never offers a move out of a closed incident", () => {
    expect(ALLOWED_TRANSITIONS.closed).toEqual([]);
    expect(ALLOWED_TRANSITIONS.resolved).toContain("closed");
  });
});
