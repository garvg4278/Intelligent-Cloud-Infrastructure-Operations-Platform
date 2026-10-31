import { useState } from "react";
import type { AuditEvent } from "../api/types";
import { Button } from "../components/Button";
import { CopyButton } from "../components/CopyButton";
import { DataTable, type Column } from "../components/DataTable";
import { EmptyState, ErrorState, Skeleton } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import { PAGE_SIZE } from "../config/constants";
import { usePaged } from "../hooks/usePaged";
import { matchesQuery } from "../lib/filter";
import { formatDateTime } from "../lib/format";
import { useAuth } from "../state/auth";

export function AuditPage() {
  const { endpoints } = useAuth();
  const [query, setQuery] = useState("");
  const list = usePaged<AuditEvent>((offset, signal) => endpoints.listAuditEvents({ limit: PAGE_SIZE, offset, signal }), [endpoints]);
  const visible = list.rows.filter((e) => matchesQuery(query, e.actor, e.action, e.resource_type, e.resource_id, e.source_service));

  const columns: Column<AuditEvent>[] = [
    { header: "When", cell: (e) => formatDateTime(e.created_at) },
    { header: "Actor", cell: (e) => e.actor },
    { header: "Action", cell: (e) => <code>{e.action}</code> },
    {
      header: "Resource",
      cell: (e) => <>{e.resource_type}{e.resource_id && <> <code className="id">{e.resource_id.slice(0, 8)}</code> <CopyButton text={e.resource_id} label="Copy resource id" /></>}</>,
      secondary: true,
    },
    { header: "Source", cell: (e) => e.source_service, secondary: true },
  ];

  return (
    <>
      <PageHeader title="Audit log" description="An append-only record of who did what. Entries cannot be edited or deleted." actions={<Button onClick={list.reload} loading={list.loading}>Refresh</Button>} />
      <div className="toolbar">
        <label className="grow">Filter loaded rows
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Actor, action, resource…" />
        </label>
      </div>
      {list.error && list.rows.length === 0 ? <ErrorState error={list.error} onRetry={list.reload} />
        : list.loading && list.rows.length === 0 ? <Skeleton rows={8} />
        : visible.length === 0 ? <EmptyState title={query ? "No events match your filter" : "No audit events yet"} />
        : <DataTable caption="Audit events" columns={columns} rows={visible} rowKey={(e) => e.id} />}
      {!list.exhausted && list.rows.length > 0 && <div className="load-more"><Button onClick={list.loadMore} loading={list.loading}>Load older events</Button></div>}
    </>
  );
}
