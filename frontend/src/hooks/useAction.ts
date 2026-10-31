import { useCallback, useState } from "react";
import { ApiError, describeError } from "../api/errors";
import { useToast } from "../state/toast";

/**
 * Wraps a mutation with a busy flag and consistent success/error toasts, so
 * every button in the app reports its outcome the same way.
 */
export function useAction<Args extends unknown[]>(
  run: (...args: Args) => Promise<unknown>,
  messages: { success: string | ((...args: Args) => string); failure: string },
  after?: () => void,
) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  const execute = useCallback(
    async (...args: Args): Promise<boolean> => {
      setBusy(true);
      try {
        await run(...args);
        toast.success(typeof messages.success === "function" ? messages.success(...args) : messages.success);
        after?.();
        return true;
      } catch (error) {
        toast.error(describeError(error, messages.failure), error instanceof ApiError ? error.requestId : null);
        return false;
      } finally {
        setBusy(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [run, toast, after],
  );
  return { execute, busy };
}
