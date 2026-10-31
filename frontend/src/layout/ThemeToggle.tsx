import { Icon } from "../components/Icon";
import { useTheme } from "../state/theme";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button type="button" className="icon-btn icon-btn-lg" onClick={toggle} aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}>
      <Icon name={theme === "dark" ? "sun" : "moon"} />
    </button>
  );
}
