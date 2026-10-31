import { useState } from "react";
import { Link } from "../app/router";
import { Button } from "../components/Button";
import { EmptyState, ErrorState, Skeleton } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { SERVICE_OPTIONS } from "../config/constants";
import { useResource } from "../hooks/useResource";
import { formatDateTime } from "../lib/format";
import { summarizeOverview } from "../lib/overview";
import { useAuth } from "../state/auth";

export function OverviewPage() {
  const { endpoints } = useAuth();
  const [service, setService] = useState<string>("gateway");

  const overview = useResource((signal) => endpoints.analyticsOverview(service, signal), [service, endpoints]);
  const incidents = useResource((signal) => endpoints.listIncidents({ limit: 5, service, signal }), [service, endpoints]);
  const alerts = useResource((signal) => endpoints.listAlerts({ limit: 5, signal }), [endpoints]);

  const cards = summarizeOverview(overview.data);
  const refreshing = overview.loading || incidents.loading || alerts.loading;
  const reloadAll = () => { overview.reload(); incidents.reload(); alerts.reload(); };

  return (
    <>
      <PageHeader
        title="Overview"
        description="Reliability, incidents and alert volume for one service at a time."
        actions={<Button onClick={reloadAll} loading={refreshing}>Refresh</Button>}
      />
      <div className="toolbar">
        <label>
          Service
          <select value={service} onChange={(e) => setService(e.target.value)}>
            {SERVICE_OPTIONS.map((name) => <option key={name}>{name}</option>)}
          </select>
        </label>
      </div>

      {overview.error ? (
        <ErrorState error={overview.error} onRetry={overview.reload} />
      ) : (
        <section aria-label="Headline numbers" className="stat-grid">
          {overview.loading && !overview.data
            ? Array.from({ length: 4 }, (_, i) => <div key={i} className="stat-card"><Skeleton rows={2} /></div>)
            : cards.map((card) => (
                <article key={card.id} className="stat-card">
                  <span>{card.label}</span>
                  <strong>{card.value}</strong>
                  <small>{card.degraded ? `Unavailable: ${card.degraded}` : card.caption}</small>
                </article>
              ))}
        </section>
      )}

      <div className="grid-2">
        <section className="panel" aria-labelledby="inc-h">
          <div className="panel-head"><h2 id="inc-h">Latest incidents · {service}</h2><Link to="/incidents">All incidents</Link></div>
          {incidents.error ? <ErrorState error={incidents.error} onRetry={incidents.reload} />
            : incidents.loading && !incidents.data ? <Skeleton />
            : incidents.data?.length ? (
              <ul className="mini-list">
                {incidents.data.map((item) => (
                  <li key={item.id}>
                    <div><strong>{item.title}</strong><small>{formatDateTime(item.created_at)}</small></div>
                    <StatusBadge value={item.severity} /><StatusBadge value={item.status} />
                  </li>
                ))}
              </ul>
            ) : <EmptyState title="No incidents">Nothing recorded for {service}.</EmptyState>}
        </section>

        <section className="panel" aria-labelledby="alr-h">
          <div className="panel-head"><h2 id="alr-h">Latest alerts</h2><Link to="/alerts">All alerts</Link></div>
          {alerts.error ? <ErrorState error={alerts.error} onRetry={alerts.reload} />
            : alerts.loading && !alerts.data ? <Skeleton />
            : alerts.data?.length ? (
              <ul className="mini-list">
                {alerts.data.map((item) => (
                  <li key={item.id}>
                    <div><strong>{item.message}</strong><small>Observed {item.observed_value} · {formatDateTime(item.fired_at)}</small></div>
                    <StatusBadge value={item.severity} /><StatusBadge value={item.status} />
                  </li>
                ))}
              </ul>
            ) : <EmptyState title="No alerts">No alert events have fired.</EmptyState>}
        </section>
      </div>
    </>
  );
}
