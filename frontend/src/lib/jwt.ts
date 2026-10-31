import type { Role } from "../api/types";

export const ROLE_RANK: Record<Role, number> = { viewer: 0, developer: 1, operator: 2, admin: 3 };

export interface TokenClaims {
  sub: string;
  role: Role;
  exp: number;
}

const isRole = (value: unknown): value is Role =>
  typeof value === "string" && Object.prototype.hasOwnProperty.call(ROLE_RANK, value);

/**
 * Reads the claims out of an access token WITHOUT verifying the signature.
 *
 * That is fine, and only fine, because the result is used purely to decide
 * which buttons to draw. The gateway verifies the real token on every request
 * and is the only thing that grants or denies access; a user who edits their
 * stored token to claim "admin" gets an admin-looking UI and a 403 on every
 * action.
 */
export function decodeClaims(token: string): TokenClaims | null {
  const part = token.split(".")[1];
  if (!part) return null;
  try {
    const base64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
    const json = new TextDecoder().decode(Uint8Array.from(atob(padded), (c) => c.charCodeAt(0)));
    const claims = JSON.parse(json) as Record<string, unknown>;
    if (typeof claims.sub !== "string" || typeof claims.exp !== "number" || !isRole(claims.role)) return null;
    return { sub: claims.sub, role: claims.role, exp: claims.exp };
  } catch {
    return null;
  }
}

export function hasRole(actual: Role | null | undefined, required: Role): boolean {
  return actual != null && ROLE_RANK[actual] >= ROLE_RANK[required];
}
