import { NAV_ITEMS } from "../app/navigation";
import { Link, useRouter } from "../app/router";
import { Icon } from "../components/Icon";
import { Logo } from "../components/Logo";
import { useAuth } from "../state/auth";
import { useConfig } from "../state/config";

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { path } = useRouter();
  const { can, email, logout } = useAuth();
  const { grafanaUrl, apiDocsUrl } = useConfig();

  return (
    <>
      {open && <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />}
      <aside id="site-nav" className="sidebar" data-open={open} aria-label="Primary">
        <div className="sidebar-head">
          <Logo onNavigate={onClose} />
          <button type="button" className="icon-btn drawer-close" onClick={onClose} aria-label="Close menu">
            <Icon name="close" />
          </button>
        </div>
        <nav aria-label="Main">
          <ul>
            {NAV_ITEMS.filter((item) => can(item.minRole)).map((item) => (
              <li key={item.to}>
                <Link to={item.to} onClick={onClose} aria-current={path === item.to ? "page" : undefined}>
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
          {(apiDocsUrl || grafanaUrl) && (
            <ul className="nav-external" aria-label="External tools">
              {apiDocsUrl && (
                <li>
                  <a href={apiDocsUrl} target="_blank" rel="noopener noreferrer">
                    API documentation <Icon name="external" size={13} />
                  </a>
                </li>
              )}
              {grafanaUrl && (
                <li>
                  <a href={grafanaUrl} target="_blank" rel="noopener noreferrer">
                    Grafana <Icon name="external" size={13} />
                  </a>
                </li>
              )}
            </ul>
          )}
        </nav>
        <div className="sidebar-foot">
          <span title={email ?? undefined}>{email}</span>
          <button type="button" className="link-btn" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>
    </>
  );
}
