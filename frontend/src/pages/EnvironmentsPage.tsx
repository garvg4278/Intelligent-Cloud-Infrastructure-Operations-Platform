import { useEffect, useState } from "react";
import type { EnvironmentType, InfraEnvironment } from "../api/types";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataTable, type Column } from "../components/DataTable";
import { EmptyState, ErrorState, Skeleton } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { useAction } from "../hooks/useAction";
import { useResource } from "../hooks/useResource";
import { formatDateTime } from "../lib/format";
import { DESTROYABLE_ENV_STATUSES, TRANSITIONAL_ENV_STATUSES } from "../lib/incidents";
import { useAuth } from "../state/auth";

const POLL_MS = 10_000;
type Pending = { kind: "provision"; type: EnvironmentType } | { kind: "destroy"; env: InfraEnvironment };

export function EnvironmentsPage() {
  const { endpoints, can } = useAuth();
  const [pending, setPending] = useState<Pending | null>(null);
  const envs = useResource((signal) => endpoints.listEnvironments(signal), [endpoints]);
  const canAct = can("admin");

  // While anything is being built or torn down, keep the list fresh.
  const working = envs.data?.some((e) => TRANSITIONAL_ENV_STATUSES.has(e.status)) ?? false;
  useEffect(() => {
    if (!working) return;
    const id = window.setInterval(envs.reload, POLL_MS);
    return () => window.clearInterval(id);
  }, [working, envs.reload]);

  const provision = useAction(
    (type: EnvironmentType) => endpoints.provisionEnvironment(type),
    { success: (type) => `Provisioning of ${type} was queued. Progress appears here and in the audit log.`, failure: "Could not queue provisioning." },
    envs.reload,
  );
  const destroy = useAction(
    (id: string) => endpoints.destroyEnvironment(id),
    { success: "Teardown was queued.", failure: "Could not queue teardown." },
    envs.reload,
  );

  const busy = provision.busy || destroy.busy;
  const columns: Column<InfraEnvironment>[] = [
    { header: "Environment", cell: (e) => <><strong>{e.name}</strong><small className="cell-sub">{e.cluster_name ?? "no cluster yet"}</small></> },
    { header: "Type", cell: (e) => e.environment_type },
    {
      header: "Status",
      cell: (e) => <><StatusBadge value={e.status} />{e.error_message && <small className="cell-sub error-text">{e.error_message}</small>}</>,
    },
    { header: "Updated", cell: (e) => formatDateTime(e.updated_at), secondary: true },
    ...(canAct
      ? [{
          header: "Actions",
          cell: (e: InfraEnvironment) =>
            DESTROYABLE_ENV_STATUSES.has(e.status)
              ? <Button variant="danger" onClick={() => setPending({ kind: "destroy", env: e })} disabled={busy}>Destroy</Button>
              : <span className="muted">—</span>,
        } satisfies Column<InfraEnvironment>]
      : []),
  ];

  async function confirm() {
    if (!pending) return;
    // Close whatever the outcome: the toast reports success or the API's refusal, and a
    // dialog left open over a failed request just blocks the page.
    if (pending.kind === "provision") await provision.execute(pending.type);
    else await destroy.execute(pending.env.id);
    setPending(null);
  }

  return (
    <>
      <PageHeader
        title="Environments"
        description="Staging and production clusters, provisioned with Terraform and configured with Ansible."
        actions={
          <>
            <Button onClick={envs.reload} loading={envs.loading}>Refresh</Button>
            {canAct && <Button variant="primary" onClick={() => setPending({ kind: "provision", type: "staging" })} disabled={busy}>Provision staging</Button>}
            {canAct && <Button variant="danger" onClick={() => setPending({ kind: "provision", type: "production" })} disabled={busy}>Provision production</Button>}
          </>
        }
      />
      {!canAct && <p className="notice notice-info">You can view environments. Provisioning and teardown require the admin role.</p>}
      {envs.error && !envs.data ? <ErrorState error={envs.error} onRetry={envs.reload} />
        : envs.loading && !envs.data ? <Skeleton rows={3} />
        : envs.data?.length ? <DataTable caption="Environments" columns={columns} rows={envs.data} rowKey={(e) => e.id} />
        : <EmptyState title="No environments yet">Provision staging or production to create the first one.</EmptyState>}

      <ConfirmDialog
        open={pending !== null}
        tone={pending?.kind === "destroy" || (pending?.kind === "provision" && pending.type === "production") ? "danger" : "primary"}
        title={pending?.kind === "destroy" ? `Destroy ${pending.env.name}?` : pending ? `Provision ${pending.type}?` : ""}
        confirmLabel={pending?.kind === "destroy" ? "Destroy environment" : "Queue provisioning"}
        busy={busy}
        onCancel={() => setPending(null)}
        onConfirm={() => void confirm()}
      >
        {pending?.kind === "destroy"
          ? <p>This runs <code>terraform destroy</code> for <strong>{pending.env.name}</strong>. Everything in the environment is deleted and cannot be recovered.</p>
          : pending && <p>This queues a Terraform apply and Ansible configuration run for a new <strong>{pending.type}</strong> environment. It creates billable cloud resources.</p>}
      </ConfirmDialog>
    </>
  );
}
