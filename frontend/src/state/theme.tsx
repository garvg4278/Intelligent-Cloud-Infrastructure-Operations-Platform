import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { STORAGE_KEYS } from "../config/constants";
import { readStorage, writeStorage } from "../lib/storage";

export type Theme = "light" | "dark";

function initialTheme(): Theme {
  const stored = readStorage(STORAGE_KEYS.theme);
  if (stored === "light" || stored === "dark") return stored;
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

const ThemeContext = createContext<{ theme: Theme; toggle: () => void } | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  const toggle = useCallback(() => {
    setTheme((current) => {
      const next = current === "dark" ? "light" : "dark";
      writeStorage(STORAGE_KEYS.theme, next);
      return next;
    });
  }, []);

  const value = useMemo(() => ({ theme, toggle }), [theme, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}
