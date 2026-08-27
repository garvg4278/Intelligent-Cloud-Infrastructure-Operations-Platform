"""HTTP clients to the platform's own services -- the deployment, alert,
and incident history an operator would actually check by hand, plus a
direct Prometheus query. Same pattern as every other cross-service call
in this repo (see the gateway's proxy.py or the alert service's
incident_client.py): a Protocol, a real httpx-based implementation, and a
fake for tests.
"""

from typing import Protocol

import httpx


class ServiceClientError(Exception):
    pass


class DeploymentClient(Protocol):
    def recent_deployments(self, service_name: str) -> list[dict]: ...


class AlertClient(Protocol):
    def recent_alerts(self, service_name: str) -> list[dict]: ...


class IncidentClient(Protocol):
    def recent_incidents(self, service_name: str) -> list[dict]: ...


class MetricsClient(Protocol):
    def query(self, promql: str) -> float: ...


class HttpDeploymentClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def recent_deployments(self, service_name: str) -> list[dict]:
        try:
            resp = httpx.get(
                f"{self.base_url}/deployments", params={"service_name": service_name}, timeout=10
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ServiceClientError(f"deployment service query failed: {exc}") from exc
        return resp.json()[:5]


class HttpAlertClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def recent_alerts(self, service_name: str) -> list[dict]:
        try:
            resp = httpx.get(
                f"{self.base_url}/alerts/rules", params={"service_name": service_name}, timeout=10
            )
            resp.raise_for_status()
            rules = resp.json()
            all_alerts_resp = httpx.get(f"{self.base_url}/alerts", timeout=10)
            all_alerts_resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ServiceClientError(f"alert service query failed: {exc}") from exc

        rule_ids = {r["id"] for r in rules}
        alerts = [a for a in all_alerts_resp.json() if a["rule_id"] in rule_ids]
        return alerts[:5]


class HttpIncidentClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def recent_incidents(self, service_name: str) -> list[dict]:
        try:
            resp = httpx.get(f"{self.base_url}/incidents", params={"service_name": service_name}, timeout=10)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ServiceClientError(f"incident service query failed: {exc}") from exc
        return resp.json()[:5]


class PrometheusClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def query(self, promql: str) -> float:
        try:
            resp = httpx.get(f"{self.base_url}/api/v1/query", params={"query": promql}, timeout=10)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ServiceClientError(f"prometheus query failed: {exc}") from exc

        data = resp.json()
        if data.get("status") != "success":
            raise ServiceClientError(f"prometheus returned a non-success status: {data}")
        result = data.get("data", {}).get("result", [])
        if not result:
            raise ServiceClientError(f"no data returned for query: {promql!r}")
        try:
            return float(result[0]["value"][1])
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise ServiceClientError(f"unexpected prometheus response shape: {data}") from exc


# Same get/set singleton pattern as every other cross-service dependency
# in this repo (redis_client.py, orchestrator.py, metrics_source.py,
# notifier.py, incident_client.py) -- lets tests inject fakes instead of
# real HTTP clients without threading them through every call site.
_deployment_client: DeploymentClient | None = None
_alert_client: AlertClient | None = None
_incident_client: IncidentClient | None = None
_metrics_client: MetricsClient | None = None


def get_deployment_client() -> DeploymentClient:
    global _deployment_client
    if _deployment_client is None:
        from .config import settings

        _deployment_client = HttpDeploymentClient(settings.DEPLOYMENT_SERVICE_URL)
    return _deployment_client


def get_alert_client() -> AlertClient:
    global _alert_client
    if _alert_client is None:
        from .config import settings

        _alert_client = HttpAlertClient(settings.ALERT_SERVICE_URL)
    return _alert_client


def get_incident_client() -> IncidentClient:
    global _incident_client
    if _incident_client is None:
        from .config import settings

        _incident_client = HttpIncidentClient(settings.INCIDENT_SERVICE_URL)
    return _incident_client


def get_metrics_client() -> MetricsClient:
    global _metrics_client
    if _metrics_client is None:
        from .config import settings

        _metrics_client = PrometheusClient(settings.PROMETHEUS_URL)
    return _metrics_client


def set_deployment_client(client: DeploymentClient | None) -> None:
    """Test hook."""
    global _deployment_client
    _deployment_client = client


def set_alert_client(client: AlertClient | None) -> None:
    """Test hook."""
    global _alert_client
    _alert_client = client


def set_incident_client(client: IncidentClient | None) -> None:
    """Test hook."""
    global _incident_client
    _incident_client = client


def set_metrics_client(client: MetricsClient | None) -> None:
    """Test hook."""
    global _metrics_client
    _metrics_client = client
