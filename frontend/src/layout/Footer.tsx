import { NAV_ITEMS } from "../app/navigation";
import { Link } from "../app/router";
import { APP_NAME } from "../config/constants";
import { CopyButton } from "../components/CopyButton";
import { useAuth } from "../state/auth";
import { useConfig } from "../state/config";

export function Footer() {
  const { can } = useAuth();
  const { supportEmail, apiDocsUrl, grafanaUrl } = useConfig();
  return (
    <footer className="site-footer">
      <nav aria-label="Footer">
        <ul>
          {NAV_ITEMS.filter((item) => can(item.minRole)).map((item) => (
            <li key={item.to}>
              <Link to={item.to}>{item.label}</Link>
            </li>
          ))}
          {apiDocsUrl && (
            <li>
              <a href={apiDocsUrl} target="_blank" rel="noopener noreferrer">API docs</a>
            </li>
          )}
          {grafanaUrl && (
            <li>
              <a href={grafanaUrl} target="_blank" rel="noopener noreferrer">Grafana</a>
            </li>
          )}
        </ul>
      </nav>
      <p>
        © {new Date().getFullYear()} {APP_NAME}. All rights reserved.
        {supportEmail && (
          <>
            {" "}
            Support: <a href={`mailto:${supportEmail}`}>{supportEmail}</a> <CopyButton text={supportEmail} label="Copy support email" />
          </>
        )}
      </p>
    </footer>
  );
}
