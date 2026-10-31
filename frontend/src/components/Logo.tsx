import { APP_NAME } from "../config/constants";
import { Link } from "../app/router";

export function Logo({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <Link to="/" className="logo" aria-label={`${APP_NAME} — go to overview`} onClick={onNavigate}>
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
        <rect width="32" height="32" rx="8" fill="currentColor" opacity=".14" />
        <path d="M16 6l9 5v10l-9 5-9-5V11z" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" />
        <circle cx="16" cy="16" r="3" fill="currentColor" />
      </svg>
      <span>{APP_NAME}</span>
    </Link>
  );
}
