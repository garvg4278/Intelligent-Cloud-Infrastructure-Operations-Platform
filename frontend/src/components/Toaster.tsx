import { useToast, useToastList } from "../state/toast";
import { CopyButton } from "./CopyButton";
import { Icon } from "./Icon";

/** Errors use role="alert" (announced immediately); success/info use role="status" (polite). */
export function Toaster() {
  const toasts = useToastList();
  const { dismiss } = useToast();
  return (
    <div className="toaster" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.tone}`} role={toast.tone === "error" ? "alert" : "status"}>
          <div className="toast-text">
            <span>{toast.message}</span>
            {toast.requestId && (
              <small>
                Ref <code>{toast.requestId.slice(0, 8)}</code> <CopyButton text={toast.requestId} label="Copy reference" />
              </small>
            )}
          </div>
          <button type="button" className="icon-btn" onClick={() => dismiss(toast.id)} aria-label="Dismiss notification">
            <Icon name="close" size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
