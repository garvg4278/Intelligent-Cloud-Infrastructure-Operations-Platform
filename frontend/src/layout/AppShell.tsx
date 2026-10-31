import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "../app/router";
import { Icon } from "../components/Icon";
import { Toaster } from "../components/Toaster";
import { useHotkey } from "../hooks/useHotkey";
import { useConfig } from "../state/config";
import { BackToTop, ScrollProgress, SkipLink } from "./Chrome";
import { CommandPalette } from "./CommandPalette";
import { Footer } from "./Footer";
import { Sidebar } from "./Sidebar";
import { ThemeToggle } from "./ThemeToggle";

export function AppShell({ children }: { children: ReactNode }) {
  const { path } = useRouter();
  const { environmentLabel } = useConfig();
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  const closeMenu = useCallback(() => setMenuOpen(false), []);
  // Never stack the palette over a confirmation dialog: both own Escape and focus.
  const openSearch = useCallback(() => {
    if (!document.body.classList.contains("modal-open")) setSearchOpen(true);
  }, []);
  const closeSearch = useCallback(() => setSearchOpen(false), []);

  useHotkey("k", openSearch);
  useHotkey("/", openSearch, { bare: true });
  useEffect(closeMenu, [path, closeMenu]);

  useEffect(() => {
    document.body.classList.toggle("menu-open", menuOpen);
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && closeMenu();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen, closeMenu]);

  return (
    <div className="shell">
      <SkipLink />
      <ScrollProgress />
      <Sidebar open={menuOpen} onClose={closeMenu} />
      <div className="shell-main">
        <header className="topbar">
          <button
            type="button"
            className="icon-btn icon-btn-lg menu-btn"
            onClick={() => setMenuOpen(true)}
            aria-label="Open menu"
            aria-expanded={menuOpen}
            aria-controls="site-nav"
          >
            <Icon name="menu" />
          </button>
          {environmentLabel && <span className="env-badge">{environmentLabel}</span>}
          <button type="button" className="search-btn" onClick={openSearch} aria-label="Search pages and actions">
            <Icon name="search" size={16} />
            <span>Search</span>
            <kbd>Ctrl K</kbd>
          </button>
          <ThemeToggle />
        </header>
        <main id="main" tabIndex={-1} className="content">
          {children}
        </main>
        <Footer />
      </div>
      <BackToTop />
      <Toaster />
      <CommandPalette open={searchOpen} onClose={closeSearch} />
    </div>
  );
}
