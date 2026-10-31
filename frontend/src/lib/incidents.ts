import type { IncidentStatus } from "../api/types";

/**
 * Mirrors services/incident/app/models.py ALLOWED_TRANSITIONS so the UI only
 * offers moves the API will accept. The server remains the authority: if the
 * two ever drift, the API's 409 is shown as an error toast.
 */
export const ALLOWED_TRANSITIONS: Record<IncidentStatus, IncidentStatus[]> = {
  open: ["acknowledged", "investigating", "resolved"],
  acknowledged: ["investigating", "resolved"],
  investigating: ["mitigated", "resolved"],
  mitigated: ["resolved"],
  resolved: ["closed", "investigating"],
  closed: [],
};

/** Moves that end or reopen an incident ask for confirmation first. */
export const NEEDS_CONFIRMATION = new Set<IncidentStatus>(["resolved", "closed"]);

export const INCIDENT_STATUSES: IncidentStatus[] = ["open", "acknowledged", "investigating", "mitigated", "resolved", "closed"];

/** Environments in these states are being worked on, so the list should keep refreshing. */
export const TRANSITIONAL_ENV_STATUSES = new Set(["pending", "provisioning_infra", "configuring_nodes", "destroying"]);
export const DESTROYABLE_ENV_STATUSES = new Set(["ready", "provision_failed", "destroy_failed"]);
