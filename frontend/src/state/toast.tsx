import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

export type ToastTone = "success" | "error" | "info";
export interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
  /** Correlation id of a failed request, shown so it can be quoted in a report. */
  requestId?: string | null;
}

interface ToastApi {
  success: (message: string) => void;
  info: (message: string) => void;
  error: (message: string, requestId?: string | null) => void;
  dismiss: (id: number) => void;
}

const MAX_VISIBLE = 4;
const DURATION_MS: Record<ToastTone, number> = { success: 5000, info: 5000, error: 9000 };

const ToastContext = createContext<{ toasts: Toast[]; api: ToastApi } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => setToasts((list) => list.filter((t) => t.id !== id)), []);

  const push = useCallback(
    (tone: ToastTone, message: string, requestId?: string | null) => {
      const id = nextId.current++;
      setToasts((list) => [...list, { id, tone, message, requestId }].slice(-MAX_VISIBLE));
      window.setTimeout(() => dismiss(id), DURATION_MS[tone]);
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(
    () => ({
      success: (m) => push("success", m),
      info: (m) => push("info", m),
      error: (m, requestId) => push("error", m, requestId),
      dismiss,
    }),
    [push, dismiss],
  );

  const value = useMemo(() => ({ toasts, api }), [toasts, api]);
  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>;
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx.api;
}

export function useToastList(): Toast[] {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToastList must be used inside <ToastProvider>");
  return ctx.toasts;
}
