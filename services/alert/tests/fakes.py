from app.incident_client import IncidentClientError
from app.metrics_source import MetricsQueryError
from app.notifier import NotifierError


class FakeMetricsSource:
    """Configure `value` to whatever the "current metric reading" should
    be for the test; flip `raise_error` to simulate Prometheus being
    unreachable or returning no data."""

    def __init__(self, value: float = 0.0, raise_error: bool = False):
        self.value = value
        self.raise_error = raise_error
        self.queries: list[str] = []

    def query(self, promql: str) -> float:
        self.queries.append(promql)
        if self.raise_error:
            raise MetricsQueryError("simulated prometheus failure")
        return self.value


class FakeNotifier:
    def __init__(self, raise_error: bool = False):
        self.raise_error = raise_error
        self.sent: list[tuple[str, dict]] = []

    def send(self, webhook_url: str, payload: dict) -> None:
        if self.raise_error:
            raise NotifierError("simulated webhook failure")
        self.sent.append((webhook_url, payload))


class FakeIncidentClient:
    def __init__(self, raise_error: bool = False):
        self.raise_error = raise_error
        self.created: list[tuple[str, str]] = []  # (alert_id, service_name)
        self._counter = 0

    def create_incident_for_alert(self, alert_id: str, rule, observed_value: float) -> str:
        if self.raise_error:
            raise IncidentClientError("simulated incident service failure")
        self._counter += 1
        incident_id = f"fake-incident-{self._counter}"
        self.created.append((alert_id, rule.service_name))
        return incident_id


class FakeAuditClient:
    def __init__(self, raise_error: bool = False):
        self.raise_error = raise_error
        self.calls: list[dict] = []

    def record(self, actor, action, resource_type, resource_id, before_state=None, after_state=None):
        if self.raise_error:
            from app.audit_client import AuditClientError

            raise AuditClientError("simulated audit service failure")
        self.calls.append(
            {
                "actor": actor,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "before_state": before_state,
                "after_state": after_state,
            }
        )
