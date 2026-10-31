import type { ComponentType } from "react";
import type { Role } from "../api/types";
import { AlertsPage } from "../pages/AlertsPage";
import { AuditPage } from "../pages/AuditPage";
import { EnvironmentsPage } from "../pages/EnvironmentsPage";
import { IncidentsPage } from "../pages/IncidentsPage";
import { OverviewPage } from "../pages/OverviewPage";
import { UsersPage } from "../pages/UsersPage";

export interface RouteDef {
  path: string;
  component: ComponentType;
  minRole: Role;
}

/** Keep in step with NAV_ITEMS (a test asserts every nav item has a route). */
export const ROUTES: readonly RouteDef[] = [
  { path: "/", component: OverviewPage, minRole: "viewer" },
  { path: "/incidents", component: IncidentsPage, minRole: "viewer" },
  { path: "/alerts", component: AlertsPage, minRole: "viewer" },
  { path: "/environments", component: EnvironmentsPage, minRole: "operator" },
  { path: "/audit", component: AuditPage, minRole: "operator" },
  { path: "/users", component: UsersPage, minRole: "admin" },
];
