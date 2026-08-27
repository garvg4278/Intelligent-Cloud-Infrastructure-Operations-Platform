"""Calls the incident service to open an incident for a newly-firing
alert. A plain HTTP call to another service, same integration pattern the
gateway already uses to reach the auth and deployment services."""

from typing import TYPE_CHECKING, Protocol

import httpx

if TYPE_CHECKING:
    from .models import AlertRule


class IncidentClientError(Exception):
    pass


class IncidentClient(Protocol):
    def create_incident_for_alert(self, alert_id: str, rule: "AlertRule", observed_value: float) -> str: ...


class HttpIncidentClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def create_incident_for_alert(self, alert_id: str, rule: "AlertRule", observed_value: float) -> str:
        payload = {
            "title": f"{rule.name} ({rule.service_name})",
            "description": (
                f"Alert rule '{rule.name}' breached: {rule.metric_query} "
                f"{rule.comparison.value} {rule.threshold} (observed {observed_value})"
            ),
            "service_name": rule.service_name,
            "severity": rule.severity.value,
            "source_alert_id": alert_id,
        }
        try:
            resp = httpx.post(f"{self.base_url}/incidents", json=payload, timeout=10)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise IncidentClientError(f"incident creation failed: {exc}") from exc
        return resp.json()["id"]


_incident_client: IncidentClient | None = None


def get_incident_client() -> IncidentClient:
    global _incident_client
    if _incident_client is None:
        from .config import settings

        _incident_client = HttpIncidentClient(settings.INCIDENT_SERVICE_URL)
    return _incident_client


def set_incident_client(client: IncidentClient | None) -> None:
    """Test hook."""
    global _incident_client
    _incident_client = client
