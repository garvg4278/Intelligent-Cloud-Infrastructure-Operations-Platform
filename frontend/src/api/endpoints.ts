import { PAGE_SIZE } from "../config/constants";
import type { ApiClient } from "./client";
import type {
  Alert,
  AnalyticsOverview,
  AuditEvent,
  EnvironmentType,
  Incident,
  IncidentStatus,
  InfraEnvironment,
  Role,
  User,
} from "./types";

export interface PageParams {
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
}

/**
 * One function per backend operation. Pages and hooks call these and never
 * build URLs themselves, so a route change is a one-line edit here.
 */
export function createEndpoints(api: ApiClient) {
  const page = ({ limit = PAGE_SIZE, offset = 0 }: PageParams) => ({ limit, offset });

  return {
    login: (email: string, password: string) => api.login(email, password),

    register: (email: string, password: string, fullName: string) =>
      api.request<User>("/auth/register", {
        method: "POST",
        anonymous: true,
        json: { email, password, full_name: fullName || null },
      }),

    analyticsOverview: (service: string, signal?: AbortSignal) =>
      api.request<AnalyticsOverview>("/analytics/overview", { query: { service_name: service }, signal }),

    listIncidents: (params: PageParams & { status?: IncidentStatus; service?: string } = {}) =>
      api.request<Incident[]>("/incidents", {
        query: { ...page(params), status_filter: params.status, service_name: params.service },
        signal: params.signal,
      }),
    transitionIncident: (id: string, status: IncidentStatus) =>
      api.request<Incident>(`/incidents/${encodeURIComponent(id)}/transition`, { method: "POST", json: { status } }),

    listAlerts: (params: PageParams & { status?: "firing" | "resolved" } = {}) =>
      api.request<Alert[]>("/alerts", { query: { ...page(params), status_filter: params.status }, signal: params.signal }),
    acknowledgeAlert: (id: string) =>
      api.request<Alert>(`/alerts/${encodeURIComponent(id)}/acknowledge`, { method: "POST" }),

    listEnvironments: (signal?: AbortSignal) =>
      api.request<InfraEnvironment[]>("/infrastructure/environments", { signal }),
    provisionEnvironment: (type: EnvironmentType) =>
      api.request<InfraEnvironment>("/infrastructure/environments", { method: "POST", json: { environment_type: type } }),
    destroyEnvironment: (id: string) =>
      api.request<InfraEnvironment>(`/infrastructure/environments/${encodeURIComponent(id)}`, { method: "DELETE" }),

    listAuditEvents: (params: PageParams = {}) =>
      api.request<AuditEvent[]>("/audit/events", { query: page(params), signal: params.signal }),

    listUsers: (signal?: AbortSignal) => api.request<User[]>("/auth/users", { signal }),
    changeRole: (userId: string, role: Role) =>
      api.request<User>(`/auth/users/${encodeURIComponent(userId)}/role`, { method: "PATCH", json: { role } }),
  };
}

export type Endpoints = ReturnType<typeof createEndpoints>;
