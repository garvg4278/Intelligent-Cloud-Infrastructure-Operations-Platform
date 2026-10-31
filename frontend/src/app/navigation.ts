import type { Role } from "../api/types";

export interface NavItem {
  to: string;
  label: string;
  description: string;
  /** Minimum role to see the item. The gateway enforces the same ladder; this just hides dead ends. */
  minRole: Role;
}

/** The single source for the sidebar, the mobile menu, the footer and search. */
export const NAV_ITEMS: readonly NavItem[] = [
  { to: "/", label: "Overview", description: "Reliability and health for a service", minRole: "viewer" },
  { to: "/incidents", label: "Incidents", description: "Open and recent incidents", minRole: "viewer" },
  { to: "/alerts", label: "Alerts", description: "Alert events and acknowledgement", minRole: "viewer" },
  { to: "/environments", label: "Environments", description: "Provision and destroy environments", minRole: "operator" },
  { to: "/audit", label: "Audit log", description: "Who changed what, and when", minRole: "operator" },
  { to: "/users", label: "Users & roles", description: "Manage access", minRole: "admin" },
];
