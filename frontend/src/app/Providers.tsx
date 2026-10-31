import type { ReactNode } from "react";
import type { RuntimeConfig } from "../config/runtime";
import { AuthProvider } from "../state/auth";
import { ConfigProvider } from "../state/config";
import { ThemeProvider } from "../state/theme";
import { ToastProvider } from "../state/toast";
import { RouterProvider } from "./router";

/** Provider order matters: toasts/theme/config first, auth (which can fire toasts' siblings) inside, router outermost-safe. */
export function Providers({ config, children, fetchImpl }: { config: RuntimeConfig; children: ReactNode; fetchImpl?: typeof fetch }) {
  return (
    <ConfigProvider value={config}>
      <ThemeProvider>
        <ToastProvider>
          <RouterProvider>
            <AuthProvider fetchImpl={fetchImpl}>{children}</AuthProvider>
          </RouterProvider>
        </ToastProvider>
      </ThemeProvider>
    </ConfigProvider>
  );
}
