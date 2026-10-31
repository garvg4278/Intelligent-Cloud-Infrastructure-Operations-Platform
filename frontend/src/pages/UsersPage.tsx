import { useState } from "react";
import type { Role, User } from "../api/types";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { DataTable, type Column } from "../components/DataTable";
import { EmptyState, ErrorState, Skeleton } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import { useAction } from "../hooks/useAction";
import { useResource } from "../hooks/useResource";
import { ROLE_RANK } from "../lib/jwt";
import { matchesQuery } from "../lib/filter";
import { formatDateTime } from "../lib/format";
import { useAuth } from "../state/auth";

const ROLES = Object.keys(ROLE_RANK) as Role[];

export function UsersPage() {
  const { endpoints, email: myEmail } = useAuth();
  const [query, setQuery] = useState("");
  const [pending, setPending] = useState<{ user: User; role: Role } | null>(null);
  const users = useResource((signal) => endpoints.listUsers(signal), [endpoints]);

  const change = useAction(
    (id: string, role: Role) => endpoints.changeRole(id, role),
    { success: (_id, role) => `Role changed to ${role}. It takes effect when the user's current session token is renewed.`, failure: "Could not change the role." },
    users.reload,
  );

  const rows = (users.data ?? []).filter((u) => matchesQuery(query, u.email, u.full_name, u.role));
  const columns: Column<User>[] = [
    { header: "User", cell: (u) => <><strong>{u.full_name || u.email}</strong>{u.full_name && <small className="cell-sub">{u.email}</small>}</> },
    { header: "Joined", cell: (u) => formatDateTime(u.created_at), secondary: true },
    {
      header: "Role",
      cell: (u) => u.email.toLowerCase() === myEmail?.toLowerCase()
        ? <span>{u.role} <span className="muted">(you)</span></span>
        : (
          <select aria-label={`Role for ${u.email}`} value={u.role} disabled={change.busy} onChange={(e) => setPending({ user: u, role: e.target.value as Role })}>
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        ),
    },
  ];

  return (
    <>
      <PageHeader title="Users & roles" description="Viewers read; developers use AI Ops; operators act on incidents, alerts and deployments; admins provision infrastructure and manage roles." actions={<Button onClick={users.reload} loading={users.loading}>Refresh</Button>} />
      <div className="toolbar"><label className="grow">Filter users<input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Name, email or role" /></label></div>
      {users.error && !users.data ? <ErrorState error={users.error} onRetry={users.reload} />
        : users.loading && !users.data ? <Skeleton rows={5} />
        : rows.length === 0 ? <EmptyState title="No users match" />
        : <DataTable caption="Users" columns={columns} rows={rows} rowKey={(u) => u.id} />}

      <ConfirmDialog
        open={pending !== null}
        tone={pending?.role === "admin" ? "danger" : "primary"}
        title={pending ? `Change role to ${pending.role}?` : ""}
        confirmLabel="Change role"
        busy={change.busy}
        onCancel={() => setPending(null)}
        onConfirm={async () => {
          if (!pending) return;
          await change.execute(pending.user.id, pending.role);
          setPending(null);
        }}
      >
        {pending && <p><strong>{pending.user.email}</strong> goes from <code>{pending.user.role}</code> to <code>{pending.role}</code>.{pending.role === "admin" && " Admins can provision and destroy infrastructure and manage every other user."} This is recorded in the audit log.</p>}
      </ConfirmDialog>
    </>
  );
}
