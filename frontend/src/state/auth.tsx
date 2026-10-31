import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { createApiClient } from "../api/client";
import { createEndpoints, type Endpoints } from "../api/endpoints";
import type { Role, Tokens } from "../api/types";
import { STORAGE_KEYS } from "../config/constants";
import { decodeClaims, hasRole } from "../lib/jwt";
import { readStorage, removeStorage, writeStorage } from "../lib/storage";

interface Session extends Tokens {
  email: string;
}

export interface AuthContextValue {
  isAuthenticated: boolean;
  email: string | null;
  role: Role | null;
  /** True when the caller's role is at least `required` (a UI hint; the gateway enforces). */
  can: (required: Role) => boolean;
  /** Set when the session ended on its own, so the login page can explain why. */
  expiredNotice: string | null;
  endpoints: Endpoints;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function parseSession(raw: string | null): Session | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<Session>;
    if (typeof value.access_token === "string" && typeof value.refresh_token === "string" && typeof value.email === "string") {
      return { access_token: value.access_token, refresh_token: value.refresh_token, email: value.email };
    }
  } catch {
    /* corrupt entry: treat as signed out */
  }
  return null;
}

export function AuthProvider({ children, fetchImpl }: { children: ReactNode; fetchImpl?: typeof fetch }) {
  const [session, setSession] = useState<Session | null>(() => parseSession(readStorage(STORAGE_KEYS.session)));
  const [expiredNotice, setExpiredNotice] = useState<string | null>(null);
  // The API client outlives renders; it reads the latest tokens through this ref.
  const sessionRef = useRef(session);

  const commit = useCallback((next: Session | null) => {
    sessionRef.current = next;
    setSession(next);
    if (next) writeStorage(STORAGE_KEYS.session, JSON.stringify(next));
    else removeStorage(STORAGE_KEYS.session);
  }, []);

  const endpoints = useMemo(() => {
    const client = createApiClient({
      fetchImpl,
      getTokens: () => sessionRef.current,
      setTokens: (tokens) => {
        if (sessionRef.current) commit({ ...tokens, email: sessionRef.current.email });
      },
      onSessionExpired: () => {
        if (sessionRef.current) {
          commit(null);
          setExpiredNotice("Your session expired. Sign in again to continue.");
        }
      },
    });
    return createEndpoints(client);
  }, [commit, fetchImpl]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await endpoints.login(email, password);
      setExpiredNotice(null);
      commit({ ...tokens, email });
    },
    [commit, endpoints],
  );

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      await endpoints.register(email, password, fullName);
      await login(email, password);
    },
    [endpoints, login],
  );

  const logout = useCallback(() => {
    setExpiredNotice(null);
    commit(null);
  }, [commit]);

  const role = useMemo(() => (session ? (decodeClaims(session.access_token)?.role ?? null) : null), [session]);

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated: session !== null,
      email: session?.email ?? null,
      role,
      can: (required) => hasRole(role, required),
      expiredNotice,
      endpoints,
      login,
      register,
      logout,
    }),
    [session, role, expiredNotice, endpoints, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
