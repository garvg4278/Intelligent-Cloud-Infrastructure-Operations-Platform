/** Wire types, mirroring the services' Pydantic response models. */

export type Role = "viewer" | "developer" | "operator" | "admin";

export interface Tokens {
  access_token: string;
  refresh_token: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export type IncidentStatus = "open" | "acknowledged" | "investigating" | "mitigated" | "resolved" | "closed";
export type Severity = "critical" | "high" | "medium" | "low";

export interface Incident {
  id: string;
  title: string;
  description: string | null;
  service_name: string;
  severity: Severity;
  status: IncidentStatus;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

export type AlertStatus = "firing" | "resolved";

export interface Alert {
  id: string;
  rule_id: string;
  status: AlertStatus;
  severity: Severity;
  message: string;
  observed_value: number;
  acknowledged_at: string | null;
  fired_at: string;
}

export type EnvironmentType = "staging" | "production";
export type EnvironmentStatus =
  | "pending"
  | "provisioning_infra"
  | "configuring_nodes"
  | "ready"
  | "provision_failed"
  | "destroying"
  | "destroyed"
  | "destroy_failed";

export interface InfraEnvironment {
  id: string;
  name: string;
  environment_type: EnvironmentType;
  status: EnvironmentStatus;
  cluster_name: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditEvent {
  id: string;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  source_service: string;
  created_at: string;
}

/** A section of the analytics overview either has data or reports why not. */
export type Section<T> = (T & { error?: undefined }) | { error: string };

export interface DeploymentStats {
  total: number;
  success_rate: number | null;
  deployments_per_day: number | null;
}
export interface IncidentStats {
  total: number;
  by_status: Record<string, number>;
  avg_resolution_seconds: number | null;
}
export interface AlertStats {
  total: number;
  by_status: Record<string, number>;
}
export interface AnalyticsOverview {
  service_name: string;
  deployments?: Section<DeploymentStats>;
  incidents?: Section<IncidentStats>;
  alerts?: Section<AlertStats>;
}
