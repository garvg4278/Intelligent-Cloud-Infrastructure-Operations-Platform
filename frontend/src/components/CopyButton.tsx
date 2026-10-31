import { useEffect, useRef, useState } from "react";
import { copyText } from "../lib/clipboard";
import { Icon } from "./Icon";

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<number>(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function onClick() {
    setState((await copyText(text)) ? "copied" : "failed");
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 2000);
  }

  return (
    <button type="button" className="icon-btn" onClick={() => void onClick()} aria-label={label} title={label}>
      <Icon name={state === "copied" ? "check" : "copy"} size={15} />
      <span className="sr-only" role="status">
        {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : ""}
      </span>
    </button>
  );
}
