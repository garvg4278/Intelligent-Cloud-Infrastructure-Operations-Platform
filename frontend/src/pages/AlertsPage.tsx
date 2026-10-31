import { useState } from "react";
import type { Alert } from "../api/types";
import { Button } from "../components/Button";
import { DataTable, type Column } from "../components/DataTable";
import { EmptyState, ErrorState, Skeleton } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { PAGE_SIZE } from "../config/constants";
import { useAction } from "../hooks/useAction";
import { usePaged } from "../hooks/usePaged";
import { matchesQuery } from "../lib/filter";
import { formatDateTime } from "../lib/format";
import { useAuth } from "../state/auth";

export function AlertsPage() {
  const { endpoints, can } = useAuth();
  const [status, setStatus] = useState<"" | "firing" | "resolved">("");
  const [query, setQuery] = useState("");

  const list = usePaged<Alert>(
    (offset, signal) => endpoints.listAlerts({ limit: PAGE_SIZE, offset, status: status || undefined, signal }),
    [status, endpoints],
  );
  const acknowledge = useAction((id: string) => endpoints.acknowledgeAlert(id), { success: "Alert acknowledged.", failure: "Could not acknowledge the alert." }, list.reload);

  const visible = list.rows.filter((a) => matchesQuery(query, a.message, a.severity));
  const canAct = can("operator");

  const columns: Column<Alert>[] = [
    { header: "Alert", cell: (a) => <><strong>{a.message}</strong><small className="cell-sub">Observed {a.observed_value}</small></> },
    { header: "Severity", cell: (a) => <StatusBadge value={a.severity} /> },
    { header: "State", cell: (a) => <StatusBadge value={a.status} /> },
    { header: "Fired", cell: (a) => formatDateTime(a.fired_at), secondary: true },
    {
      header: "Acknowledged",
      cell: (a) => a.acknowledged_at ? formatDateTime(a.acknowledged_at)
        : canAct && a.status === "firing"
          ? <Button onClick={() => void acknowledge.execute(a.id)} disabled={acknowledge.busy}>Acknowledge</Button>
          : <span className="muted">—</span>,
    },
  ];

  return (
    <>
      <PageHeader title="Alerts" description="Events raised by alert rules evaluated against Prometheus." actions={<Button onClick={list.reload} loading={list.loading}>Refresh</Button>} />
      <div className="toolbar">
        <label>State
          <select value={status} onChange={(e) => setStatus(e.target.value as typeof status)}>
            <option value="">All</option><option value="firing">Firing</option><option value="resolved">Resolved</option>
          </select>
        </label>
        <label className="grow">Filter loaded rows
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Message or severity" />
        </label>
      </div>
      {list.error && list.rows.length === 0 ? <ErrorState error={list.error} onRetry={list.reload} />
        : list.loading && list.rows.length === 0 ? <Skeleton rows={6} />
        : visible.length === 0 ? <EmptyState title={query ? "No alerts match your filter" : "No alerts"}>{query ? "Clear the filter to see all loaded rows." : "No alert events match this state."}</EmptyState>
        : <DataTable caption="Alerts" columns={columns} rows={visible} rowKey={(a) => a.id} />}
      {!list.exhausted && list.rows.length > 0 && <div className="load-more"><Button onClick={list.loadMore} loading={list.loading}>Load more</Button></div>}
    </>
  );
}
