import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type RecordValue = Record<string, unknown>;

type Session = {
  access_token: string;
  refresh_token: string;
  email: string;
};

const SERVICE_OPTIONS = ["gateway", "auth", "deployment", "alert", "incident", "aiops"];
const sessionStorageKey = "icop-session";

function readSession(): Session | null {
  try {
    const stored = window.localStorage.getItem(sessionStorageKey);
    return stored ? (JSON.parse(stored) as Session) : null;
  } catch {
    return null;
  }
}

async function api<T>(path: string, token?: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api/v1${path}`, { ...init, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as RecordValue;
    throw new Error(String(body.detail ?? `Request failed (${response.status})`));
  }
  return response.json() as Promise<T>;
}

function metric(value: unknown): string {
  if (typeof value === "number") return Intl.NumberFormat().format(value);
  return value == null ? "—" : String(value);
}

function App() {
  const [session, setSession] = useState<Session | null>(readSession);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [isRegistering, setIsRegistering] = useState(false);
  const [service, setService] = useState("gateway");
  const [overview, setOverview] = useState<RecordValue | null>(null);
  const [incidents, setIncidents] = useState<RecordValue[]>([]);
  const [alerts, setAlerts] = useState<RecordValue[]>([]);
  const [environments, setEnvironments] = useState<RecordValue[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const logout = useCallback(() => {
    window.localStorage.removeItem(sessionStorageKey);
    setSession(null);
    setOverview(null);
  }, []);

  const loadDashboard = useCallback(async () => {
    if (!session) return;
    setLoading(true);
    setError("");
    try {
      const [nextOverview, nextIncidents, nextAlerts, nextEnvironments] = await Promise.all([
        api<RecordValue>(`/analytics/overview?service_name=${encodeURIComponent(service)}`, session.access_token),
        api<RecordValue[]>("/incidents?limit=8", session.access_token),
        api<RecordValue[]>("/alerts?limit=8", session.access_token),
        api<RecordValue[]>("/infrastructure/environments", session.access_token),
      ]);
      setOverview(nextOverview);
      setIncidents(nextIncidents);
      setAlerts(nextAlerts);
      setEnvironments(nextEnvironments);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load operational data.");
    } finally {
      setLoading(false);
    }
  }, [service, session]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const counters = useMemo(() => {
    const deployments = (overview?.deployments as RecordValue | undefined) ?? {};
    const incidentStats = (overview?.incidents as RecordValue | undefined) ?? {};
    const alertStats = (overview?.alerts as RecordValue | undefined) ?? {};
    return [
      ["Deployment success", metric(deployments.success_rate), "release reliability"],
      ["Open incidents", metric(incidentStats.open_count), "needs response"],
      ["Active alerts", metric(alertStats.active_count), "signal volume"],
      ["Total deployments", metric(deployments.total), "tracked releases"],
    ];
  }, [overview]);

  async function authenticate(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    setLoading(true);
    try {
      if (isRegistering) {
        await api("/auth/register", undefined, {
          method: "POST",
          body: JSON.stringify({ email, password, full_name: fullName || null }),
        });
      }
      const body = new URLSearchParams({ username: email, password });
      const response = await fetch("/api/v1/auth/login", { method: "POST", body });
      if (!response.ok) throw new Error("Sign-in failed. Check your email and password.");
      const tokens = (await response.json()) as Omit<Session, "email">;
      const nextSession = { ...tokens, email };
      window.localStorage.setItem(sessionStorageKey, JSON.stringify(nextSession));
      setSession(nextSession);
      setNotice(isRegistering ? "Account created. Your operations console is ready." : "Authenticated successfully.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to authenticate.");
    } finally {
      setLoading(false);
    }
  }

  async function provision(environmentType: "staging" | "production") {
    if (!session) return;
    setNotice("");
    setError("");
    try {
      await api("/infrastructure/environments", session.access_token, {
        method: "POST",
        body: JSON.stringify({ environment_type: environmentType }),
      });
      setNotice(`${environmentType} provisioning was queued. The worker will record its progress in the audit trail.`);
      void loadDashboard();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to queue provisioning.");
    }
  }

  if (!session) {
    return <main className="login-shell">
      <section className="brand-panel">
        <div className="eyebrow">ICOP / CONTROL PLANE</div>
        <h1>Operate cloud infrastructure with evidence, not guesswork.</h1>
        <p>Deploy, observe, respond, audit, and automate through one secure operations console.</p>
        <div className="capability-list"><span>10 services</span><span>JWT + RBAC</span><span>Prometheus</span><span>GitOps</span></div>
      </section>
      <section className="auth-panel">
        <div className="logo"><span>◈</span> ICOP</div>
        <h2>{isRegistering ? "Create an operator account" : "Welcome back"}</h2>
        <p>{isRegistering ? "Start with a local account for the development control plane." : "Sign in to view operational data."}</p>
        <form onSubmit={authenticate}>
          {isRegistering && <label>Full name<input value={fullName} onChange={(event) => setFullName(event.target.value)} autoComplete="name" /></label>}
          <label>Work email<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required /></label>
          <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} autoComplete={isRegistering ? "new-password" : "current-password"} required /></label>
          {error && <div className="message error">{error}</div>}
          <button className="primary" disabled={loading}>{loading ? "Working…" : isRegistering ? "Create account" : "Sign in"}</button>
        </form>
        <button className="link-button" onClick={() => setIsRegistering((value) => !value)}>{isRegistering ? "Already have an account? Sign in" : "Need an account? Register"}</button>
      </section>
    </main>;
  }

  return <main className="app-shell">
    <aside>
      <div className="logo"><span>◈</span> ICOP</div>
      <div className="environment-badge"><i /> Production posture</div>
      <nav><a className="active" href="#overview">Overview</a><a href="#incidents">Incidents</a><a href="#alerts">Alerts</a><a href="/docs" target="_blank" rel="noreferrer">API documentation ↗</a><a href="http://localhost:3000" target="_blank" rel="noreferrer">Grafana ↗</a></nav>
      <div className="sidebar-foot"><span>{session.email}</span><button onClick={logout}>Sign out</button></div>
    </aside>
    <section className="workspace">
      <header><div><div className="eyebrow">LIVE OPERATIONS</div><h1>Infrastructure command center</h1><p>Correlate releases, incidents, alerts, and environment state in one place.</p></div><button className="secondary" onClick={() => void loadDashboard()} disabled={loading}>{loading ? "Refreshing…" : "Refresh data"}</button></header>
      {notice && <div className="message success">{notice}</div>}{error && <div className="message error">{error}</div>}
      <section id="overview" className="overview-controls"><label>Service scope<select value={service} onChange={(event) => setService(event.target.value)}>{SERVICE_OPTIONS.map((option) => <option key={option}>{option}</option>)}</select></label><div className="signal"><i /> Signals refresh from live service APIs</div></section>
      <section className="stat-grid">{counters.map(([title, value, caption]) => <article className="stat-card" key={title}><span>{title}</span><strong>{value}</strong><small>{caption}</small></article>)}</section>
      <section className="two-col"><article className="panel"><div className="panel-heading"><div><span className="eyebrow">ENVIRONMENTS</span><h2>Provisioning control</h2></div><div className="button-group"><button onClick={() => void provision("staging")}>Queue staging</button><button onClick={() => void provision("production")}>Queue production</button></div></div><div className="table">{environments.length ? environments.map((item) => <div className="row" key={String(item.id)}><strong>{String(item.name)}</strong><span>{String(item.environment_type)}</span><span className={`status ${String(item.status)}`}>{String(item.status)}</span></div>) : <div className="empty">No environments registered yet. Queue provisioning to create an audited request.</div>}</div></article><article className="panel"><div className="panel-heading"><div><span className="eyebrow">AUTOMATION</span><h2>Platform capabilities</h2></div></div><ul className="capabilities"><li><b>GitOps ready</b><span>Argo CD ApplicationSets and Helm values are versioned.</span></li><li><b>Observable by default</b><span>Prometheus metrics, Grafana dashboards, correlation IDs.</span></li><li><b>Secure control plane</b><span>Gateway JWT enforcement, rate limits, audit events, image scans.</span></li></ul></article></section>
      <section id="incidents" className="two-col"><article className="panel"><div className="panel-heading"><div><span className="eyebrow">INCIDENTS</span><h2>Latest response work</h2></div></div><div className="table">{incidents.length ? incidents.map((item) => <div className="row detail" key={String(item.id)}><div><strong>{String(item.title)}</strong><small>{String(item.service_name)}</small></div><span className={`severity ${String(item.severity)}`}>{String(item.severity)}</span><span className={`status ${String(item.status)}`}>{String(item.status)}</span></div>) : <div className="empty">No incidents in the current data set.</div>}</div></article><article id="alerts" className="panel"><div className="panel-heading"><div><span className="eyebrow">ALERTS</span><h2>Recent signals</h2></div></div><div className="table">{alerts.length ? alerts.map((item) => <div className="row detail" key={String(item.id)}><div><strong>{String(item.message)}</strong><small>Observed {metric(item.observed_value)}</small></div><span className={`severity ${String(item.severity)}`}>{String(item.severity)}</span><span className={`status ${String(item.status)}`}>{String(item.status)}</span></div>) : <div className="empty">No alert events in the current data set.</div>}</div></article></section>
    </section>
  </main>;
}

createRoot(document.getElementById("root")!).render(<App />);
