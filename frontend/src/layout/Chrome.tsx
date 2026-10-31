import { useScroll } from "../hooks/useScroll";
import { Icon } from "../components/Icon";

export const SkipLink = () => (
  <a className="skip-link" href="#main">
    Skip to main content
  </a>
);

export function ScrollProgress() {
  const { progress } = useScroll();
  return (
    <div className="scroll-progress" aria-hidden="true">
      <div className="scroll-progress-bar" ref={(el) => el?.style.setProperty("--progress", String(progress))} />
    </div>
  );
}

export function BackToTop() {
  const { scrolled } = useScroll();
  if (!scrolled) return null;
  return (
    <button
      type="button"
      className="back-to-top"
      aria-label="Back to top"
      onClick={() => window.scrollTo({ top: 0, behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" })}
    >
      <Icon name="up" />
    </button>
  );
}
