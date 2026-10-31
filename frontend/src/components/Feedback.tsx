import type { ReactNode } from "react";
import { ApiError } from "../api/errors";
import { Button } from "./Button";
import { CopyButton } from "./CopyButton";

export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="skeleton" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} className="skeleton-row" />
      ))}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const api = error instanceof ApiError ? error : null;
  const denied = api?.isForbidden;
  return (
    <div className="error-state" role="alert">
      <strong>{denied ? "You don't have access to this" : "Couldn't load this"}</strong>
      <p>{denied ? "Your role doesn't include this view. Ask an admin if you need it." : error.message}</p>
      {api?.requestId && (
        <p className="muted">
          Reference <code>{api.requestId}</code> <CopyButton text={api.requestId} label="Copy reference" />
        </p>
      )}
      {onRetry && !denied && (
        <Button onClick={onRetry} variant="secondary">
          Try again
        </Button>
      )}
    </div>
  );
}
