import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, describeError } from "../api/errors";
import { Button } from "../components/Button";
import { Logo } from "../components/Logo";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { ThemeToggle } from "../layout/ThemeToggle";
import { useAuth } from "../state/auth";

const MIN_PASSWORD = 8;
const MAX_PASSWORD_BYTES = 72; // bcrypt's limit, mirrored from the auth service

export function LoginPage() {
  const { login, register, expiredNotice } = useAuth();
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const registering = mode === "register";

  useDocumentTitle(registering ? "Create account" : "Sign in");
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  function validate(): string | null {
    if (password.length < MIN_PASSWORD) return `Password must be at least ${MIN_PASSWORD} characters.`;
    if (new TextEncoder().encode(password).length > MAX_PASSWORD_BYTES) return `Password must be at most ${MAX_PASSWORD_BYTES} bytes.`;
    return null;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const problem = registering ? validate() : null;
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      if (registering) await register(email.trim(), password, fullName.trim());
      else await login(email.trim(), password);
    } catch (reason) {
      setError(describeError(reason, "Unable to sign in."));
      if (reason instanceof ApiError && reason.status === 0) setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <a className="skip-link" href="#main">Skip to main content</a>
      <section className="login-hero" aria-labelledby="hero-title">
        <Logo />
        <h1 id="hero-title">Operate cloud infrastructure with evidence, not guesswork.</h1>
        <p>Deployments, incidents, alerts, environments and the audit trail — one console, every action authorised and recorded.</p>
      </section>
      <main id="main" className="login-panel" tabIndex={-1}>
        <div className="login-theme"><ThemeToggle /></div>
        <h2>{registering ? "Create your account" : "Sign in"}</h2>
        <p className="muted">
          {registering ? "New accounts start with read-only access. An admin can grant more." : "Use the account for this ICOP deployment."}
        </p>
        {expiredNotice && !error && <div className="notice notice-info" role="status">{expiredNotice}</div>}
        <form onSubmit={(e) => void onSubmit(e)} noValidate={false}>
          {registering && (
            <label>
              Full name <span className="optional">(optional)</span>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" maxLength={255} />
            </label>
          )}
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required inputMode="email" />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={registering ? "new-password" : "current-password"}
              required
              aria-describedby={registering ? "pw-hint" : undefined}
            />
            {registering && <small id="pw-hint" className="muted">At least {MIN_PASSWORD} characters.</small>}
          </label>
          {error && (
            <div className="notice notice-error" role="alert" tabIndex={-1} ref={errorRef}>
              {error}
            </div>
          )}
          <Button type="submit" variant="primary" loading={busy}>
            {busy ? "Working…" : registering ? "Create account" : "Sign in"}
          </Button>
        </form>
        <button
          type="button"
          className="link-btn"
          onClick={() => {
            setMode(registering ? "signin" : "register");
            setError(null);
          }}
        >
          {registering ? "Already have an account? Sign in" : "Need an account? Register"}
        </button>
      </main>
    </div>
  );
}
