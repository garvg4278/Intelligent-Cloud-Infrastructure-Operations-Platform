import type { AnalyticsOverview, Section } from "../api/types";
import { formatDuration, formatNumber, formatPercent } from "./format";

export interface StatCard {
  id: string;
  label: string;
  value: string;
  caption: string;
  /** Set when this card's section of the overview could not be computed. */
  degraded?: string;
}

const CLOSED = new Set(["resolved", "closed"]);

/**
 * Turns the analytics response into the four headline numbers.
 *
 * The API reports `by_status` counts, not `open_count`/`active_count`, so the
 * "open incidents" and "active alerts" figures are derived here. (The previous
 * console read keys that don't exist and silently displayed "—" for both.)
 * A section that failed upstream arrives as `{error}` and is shown as degraded
 * instead of as a misleading zero.
 */
function ok<T>(section: Section<T> | undefined): section is T & { error?: undefined } {
  return section !== undefined && section.error === undefined;
}

export function summarizeOverview(overview: AnalyticsOverview | null): StatCard[] {
  const deployments = overview?.deployments;
  const incidents = overview?.incidents;
  const alerts = overview?.alerts;
  const deploymentError = deployments && !ok(deployments) ? deployments.error : undefined;
  const incidentError = incidents && !ok(incidents) ? incidents.error : undefined;
  const alertError = alerts && !ok(alerts) ? alerts.error : undefined;

  const openIncidents = ok(incidents)
    ? Object.entries(incidents.by_status).reduce((sum, [status, n]) => (CLOSED.has(status) ? sum : sum + n), 0)
    : null;

  return [
    {
      id: "success",
      label: "Deployment success",
      value: ok(deployments) ? formatPercent(deployments.success_rate) : "—",
      caption: ok(deployments) ? `${formatNumber(deployments.total)} deployments tracked` : "release reliability",
      degraded: deploymentError,
    },
    {
      id: "open-incidents",
      label: "Open incidents",
      value: formatNumber(openIncidents),
      caption: ok(incidents) ? `mean time to resolve ${formatDuration(incidents.avg_resolution_seconds)}` : "needs response",
      degraded: incidentError,
    },
    {
      id: "firing-alerts",
      label: "Firing alerts",
      value: ok(alerts) ? formatNumber(alerts.by_status.firing ?? 0) : "—",
      caption: ok(alerts) ? `${formatNumber(alerts.total)} alert events in total` : "signal volume",
      degraded: alertError,
    },
    {
      id: "frequency",
      label: "Deploys per day",
      value: ok(deployments) ? formatNumber(deployments.deployments_per_day) : "—",
      caption: "average release cadence",
      degraded: deploymentError,
    },
  ];
}
