"""HTTP clients to the deployment/incident/alert services -- same pattern
as every other cross-service call in this repo, but these fetch the FULL
matching list rather than capping at a handful, since accurate statistics
need the whole dataset, not a recent sample.
"""

from typing import Protocol

import httpx


class ServiceClientError(Exception):
    pass


class DeploymentClient(Protocol):
    def all_deployments(self, service_name: str) -> list[dict]: ...


class IncidentClient(Protocol):
    def all_incidents(self, service_name: str) -> list[dict]: ...


class AlertClient(Protocol):
    def all_alerts(self, service_name: str) -> tuple[list[dict], list[dict]]:
        """Returns (rules_for_this_service, all_alerts) -- the caller
        joins them, same reasoning as the aiops service's alert client:
        the alert service doesn't expose "alerts for this service"
        directly, only "alerts for this rule" via the rule relationship.
        """
        ...


class HttpDeploymentClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def all_deployments(self, service_name: str) -> list[dict]:
        try:
            resp = httpx.get(
                f"{self.base_url}/deployments", params={"service_name": service_name}, timeout=10
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ServiceClientError(f"deployment service query failed: {exc}") from exc
        return resp.json()


class HttpIncidentClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def all_incidents(self, service_name: str) -> list[dict]:
        try:
            resp = httpx.get(
                f"{self.base_url}/incidents", params={"service_name": service_name}, timeout=10
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ServiceClientError(f"incident service query failed: {exc}") from exc
        return resp.json()


class HttpAlertClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def all_alerts(self, service_name: str) -> tuple[list[dict], list[dict]]:
        try:
            rules_resp = httpx.get(
                f"{self.base_url}/alerts/rules", params={"service_name": service_name}, timeout=10
            )
            rules_resp.raise_for_status()
            alerts_resp = httpx.get(f"{self.base_url}/alerts", timeout=10)
            alerts_resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ServiceClientError(f"alert service query failed: {exc}") from exc

        rules = rules_resp.json()
        rule_ids = {r["id"] for r in rules}
        alerts = [a for a in alerts_resp.json() if a["rule_id"] in rule_ids]
        return rules, alerts


_deployment_client: DeploymentClient | None = None
_incident_client: IncidentClient | None = None
_alert_client: AlertClient | None = None


def get_deployment_client() -> DeploymentClient:
    global _deployment_client
    if _deployment_client is None:
        from .config import settings

        _deployment_client = HttpDeploymentClient(settings.DEPLOYMENT_SERVICE_URL)
    return _deployment_client


def get_incident_client() -> IncidentClient:
    global _incident_client
    if _incident_client is None:
        from .config import settings

        _incident_client = HttpIncidentClient(settings.INCIDENT_SERVICE_URL)
    return _incident_client


def get_alert_client() -> AlertClient:
    global _alert_client
    if _alert_client is None:
        from .config import settings

        _alert_client = HttpAlertClient(settings.ALERT_SERVICE_URL)
    return _alert_client


def set_deployment_client(client: DeploymentClient | None) -> None:
    global _deployment_client
    _deployment_client = client


def set_incident_client(client: IncidentClient | None) -> None:
    global _incident_client
    _incident_client = client


def set_alert_client(client: AlertClient | None) -> None:
    global _alert_client
    _alert_client = client
