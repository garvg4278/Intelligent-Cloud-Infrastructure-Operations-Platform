import { useEffect } from "react";

const isTypingTarget = (target: EventTarget | null) =>
  target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

/** Calls `handler` for Ctrl/Cmd+<key>, or for the bare key when `bare` is set and the user isn't typing. */
export function useHotkey(key: string, handler: () => void, options: { bare?: boolean } = {}): void {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== key.toLowerCase()) return;
      const combo = event.ctrlKey || event.metaKey;
      if (combo || (options.bare && !event.altKey && !isTypingTarget(event.target))) {
        event.preventDefault();
        handler();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [key, handler, options.bare]);
}
