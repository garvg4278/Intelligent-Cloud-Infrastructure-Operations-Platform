import { useState } from "react";
import type { Incident, IncidentStatus } from "../api/types";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataTable, type Column } from "../components/DataTable";
import { EmptyState, ErrorState, Skeleton } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { useAction } from "../hooks/useAction";
import { usePaged } from "../hooks/usePaged";
import { formatDateTime, humanize } from "../lib/format";
import { matchesQuery } from "../lib/filter";
import { ALLOWED_TRANSITIONS, INCIDENT_STATUSES, NEEDS_CONFIRMATION } from "../lib/incidents";
import { PAGE_SIZE } from "../config/constants";
import { useAuth } from "../state/auth";

export function IncidentsPage() {
  const { endpoints, can } = useAuth();
  const [status, setStatus] = useState<IncidentStatus | "">("");
  const [query, setQuery] = useState("");
  const [pending, setPending] = useState<{ incident: Incident; to: IncidentStatus } | null>(null);

  const list = usePaged<Incident>(
    (offset, signal) => endpoints.listIncidents({ limit: PAGE_SIZE, offset, status: status || undefined, signal }),
    [status, endpoints],
  );

  const transition = useAction(
    (id: string, to: IncidentStatus) => endpoints.transitionIncident(id, to),
    { success: (_id, to) => `Incident moved to ${humanize(to)}.`, failure: "Could not update the incident." },
    list.reload,
  );

  const canAct = can("operator");
  const visible = list.rows.filter((i) => matchesQuery(query, i.title, i.service_name, i.description));

  async function apply(incident: Incident, to: IncidentStatus) {
    if (NEEDS_CONFIRMATION.has(to)) return setPending({ incident, to });
    await transition.execute(incident.id, to);
  }

  const columns: Column<Incident>[] = [
    { header: "Incident", cell: (i) => <><strong>{i.title}</strong><small className="cell-sub">{i.service_name}</small></> },
    { header: "Severity", cell: (i) => <StatusBadge value={i.severity} /> },
    { header: "Status", cell: (i) => <StatusBadge value={i.status} /> },
    { header: "Opened", cell: (i) => formatDateTime(i.created_at), secondary: true },
    ...(canAct
      ? [{
          header: "Move to",
          cell: (i: Incident) => {
            const options = ALLOWED_TRANSITIONS[i.status];
            return options.length === 0 ? <span className="muted">Final</span> : (
              <select
                aria-label={`Move “${i.title}” to`}
                value=""
                disabled={transition.busy}
                onChange={(e) => e.target.value && void apply(i, e.target.value as IncidentStatus)}
              >
                <option value="">Choose…</option>
                {options.map((o) => <option key={o} value={o}>{humanize(o)}</option>)}
              </select>
            );
          },
        } satisfies Column<Incident>]
      : []),
  ];

  return (
    <>
      <PageHeader title="Incidents" description="Track response work from detection to closure." actions={<Button onClick={list.reload} loading={list.loading}>Refresh</Button>} />
      <div className="toolbar">
        <label>Status
          <select value={status} onChange={(e) => setStatus(e.target.value as IncidentStatus | "")}>
            <option value="">All</option>
            {INCIDENT_STATUSES.map((s) => <option key={s} value={s}>{humanize(s)}</option>)}
          </select>
        </label>
        <label className="grow">Filter loaded rows
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Title or service" />
        </label>
      </div>

      {list.error && list.rows.length === 0 ? <ErrorState error={list.error} onRetry={list.reload} />
        : list.loading && list.rows.length === 0 ? <Skeleton rows={6} />
        : visible.length === 0 ? <EmptyState title={query ? "No incidents match your filter" : "No incidents"}>{query ? "Clear the filter to see all loaded rows." : "Nothing has been reported with this status."}</EmptyState>
        : <DataTable caption="Incidents" columns={columns} rows={visible} rowKey={(i) => i.id} />}

      {!list.exhausted && list.rows.length > 0 && (
        <div className="load-more"><Button onClick={list.loadMore} loading={list.loading}>Load more</Button></div>
      )}

      <ConfirmDialog
        open={pending !== null}
        title={pending ? `Move to “${humanize(pending.to)}”?` : ""}
        confirmLabel={pending ? `Mark ${humanize(pending.to)}` : "Confirm"}
        busy={transition.busy}
        onCancel={() => setPending(null)}
        onConfirm={async () => {
          if (!pending) return;
          await transition.execute(pending.incident.id, pending.to);
          setPending(null);
        }}
      >
        {pending && <p><strong>{pending.incident.title}</strong> will be recorded as {humanize(pending.to)} in the incident timeline.</p>}
      </ConfirmDialog>
    </>
  );
}
