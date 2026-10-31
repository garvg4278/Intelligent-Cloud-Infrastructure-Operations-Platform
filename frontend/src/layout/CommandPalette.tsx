import { useEffect, useId, useMemo, useRef, useState } from "react";
import { NAV_ITEMS } from "../app/navigation";
import { useRouter } from "../app/router";
import { useAuth } from "../state/auth";
import { useConfig } from "../state/config";
import { useTheme } from "../state/theme";

interface Command {
  id: string;
  label: string;
  hint: string;
  run: () => void;
}

/** Ctrl/Cmd+K: search pages and actions. */
export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { navigate } = useRouter();
  const { can, logout } = useAuth();
  const { toggle: toggleTheme } = useTheme();
  const { apiDocsUrl, grafanaUrl } = useConfig();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();

  const commands = useMemo<Command[]>(() => {
    const list: Command[] = NAV_ITEMS.filter((i) => can(i.minRole)).map((i) => ({
      id: i.to, label: i.label, hint: i.description, run: () => navigate(i.to),
    }));
    list.push({ id: "theme", label: "Toggle dark mode", hint: "Switch between light and dark", run: toggleTheme });
    if (apiDocsUrl) list.push({ id: "docs", label: "API documentation", hint: "Opens in a new tab", run: () => window.open(apiDocsUrl, "_blank", "noopener,noreferrer") });
    if (grafanaUrl) list.push({ id: "grafana", label: "Grafana", hint: "Opens in a new tab", run: () => window.open(grafanaUrl, "_blank", "noopener,noreferrer") });
    list.push({ id: "signout", label: "Sign out", hint: "End this session", run: logout });
    return list;
  }, [can, navigate, toggleTheme, apiDocsUrl, grafanaUrl, logout]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? commands.filter((c) => `${c.label} ${c.hint}`.toLowerCase().includes(q)) : commands;
  }, [commands, query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      input.current?.focus();
    }
  }, [open]);
  useEffect(() => setActive(0), [query]);

  if (!open) return null;

  const choose = (command: Command | undefined) => {
    if (!command) return;
    onClose();
    command.run();
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") onClose();
    else if (event.key === "ArrowDown") { event.preventDefault(); setActive((i) => Math.min(i + 1, results.length - 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
    else if (event.key === "Enter") { event.preventDefault(); choose(results[active]); }
  };

  return (
    <div className="modal-backdrop palette-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Search pages and actions" onKeyDown={onKeyDown}>
        <input
          ref={input}
          type="search"
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-activedescendant={results[active] ? `${listId}-${active}` : undefined}
          aria-label="Search pages and actions"
          placeholder="Search pages and actions…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoComplete="off"
        />
        <ul id={listId} role="listbox">
          {results.map((command, index) => (
            <li
              key={command.id}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(command)}
            >
              <strong>{command.label}</strong>
              <small>{command.hint}</small>
            </li>
          ))}
          {results.length === 0 && <li className="palette-empty" role="presentation">No matches for “{query}”.</li>}
        </ul>
      </div>
    </div>
  );
}
