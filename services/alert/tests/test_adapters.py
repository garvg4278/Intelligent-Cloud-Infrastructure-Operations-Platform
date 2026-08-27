"""Unit tests for the three real HTTP-based adapters, each with the
underlying httpx call mocked -- same spirit as the deployment service's
test_orchestrator.py: these prove MY code builds the right request and
parses the response correctly, not that the real remote service behaves
as expected (no live Prometheus, webhook receiver, or incident service is
available here).
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.incident_client import HttpIncidentClient, IncidentClientError
from app.metrics_source import MetricsQueryError, PrometheusMetricsSource
from app.models import AlertRule, AlertSeverity, Comparison
from app.notifier import HttpNotificationClient, NotifierError

# --- PrometheusMetricsSource -------------------------------------------------


def test_prometheus_source_parses_successful_instant_query():
    source = PrometheusMetricsSource("http://prom:9090")
    fake_response = MagicMock(
        status_code=200,
        json=lambda: {
            "status": "success",
            "data": {"resultType": "vector", "result": [{"metric": {}, "value": [1700000000, "0.42"]}]},
        },
    )
    fake_response.raise_for_status = lambda: None

    with patch("app.metrics_source.httpx.get", return_value=fake_response) as mock_get:
        value = source.query('rate(http_requests_total{status=~"5.."}[5m])')

    assert value == 0.42
    called_url, called_kwargs = mock_get.call_args
    assert called_url[0] == "http://prom:9090/api/v1/query"
    assert called_kwargs["params"]["query"] == 'rate(http_requests_total{status=~"5.."}[5m])'


def test_prometheus_source_raises_on_empty_result():
    source = PrometheusMetricsSource("http://prom:9090")
    fake_response = MagicMock(json=lambda: {"status": "success", "data": {"result": []}})
    fake_response.raise_for_status = lambda: None

    with (
        patch("app.metrics_source.httpx.get", return_value=fake_response),
        pytest.raises(MetricsQueryError, match="no data"),
    ):
        source.query("some_metric_with_no_series")


def test_prometheus_source_raises_on_non_success_status():
    source = PrometheusMetricsSource("http://prom:9090")
    fake_response = MagicMock(json=lambda: {"status": "error", "error": "bad query syntax"})
    fake_response.raise_for_status = lambda: None

    with (
        patch("app.metrics_source.httpx.get", return_value=fake_response),
        pytest.raises(MetricsQueryError, match="non-success"),
    ):
        source.query("((( invalid promql")


def test_prometheus_source_raises_on_connection_failure():
    source = PrometheusMetricsSource("http://prom:9090")
    with (
        patch("app.metrics_source.httpx.get", side_effect=httpx.ConnectError("boom")),
        pytest.raises(MetricsQueryError, match="prometheus query failed"),
    ):
        source.query("up")


# --- HttpNotificationClient ---------------------------------------------------


def test_notification_client_posts_to_notification_service_not_the_webhook_url():
    client = HttpNotificationClient("http://notification-service:8000")
    fake_response = MagicMock(status_code=202)
    fake_response.raise_for_status = lambda: None

    with patch("app.notifier.httpx.post", return_value=fake_response) as mock_post:
        client.send(
            "https://hooks.example.com/x",
            {
                "alert_id": "abc", "rule_name": "high error rate", "service_name": "auth",
                "severity": "critical", "message": "high error rate: rate(...) gt 0.05 (observed 0.42)",
            },
        )

    called_url, called_kwargs = mock_post.call_args
    # The real destination is the notification service, NOT the webhook
    # URL directly -- that's the entire point of this integration.
    assert called_url[0] == "http://notification-service:8000/notifications"
    body = called_kwargs["json"]
    assert body["channel"] == "webhook"
    assert body["target"] == "https://hooks.example.com/x"  # webhook_url is preserved as the target
    assert body["subject"] == "[CRITICAL] high error rate (auth)"
    assert body["body"] == "high error rate: rate(...) gt 0.05 (observed 0.42)"


def test_notification_client_falls_back_to_json_body_if_no_message_field():
    client = HttpNotificationClient("http://notification-service:8000")
    fake_response = MagicMock(status_code=202)
    fake_response.raise_for_status = lambda: None

    with patch("app.notifier.httpx.post", return_value=fake_response) as mock_post:
        client.send("https://hooks.example.com/x", {"alert_id": "abc"})

    body = mock_post.call_args[1]["json"]
    assert "abc" in body["body"]  # the raw payload, JSON-encoded, since "message" was absent


def test_notification_client_raises_notifier_error_on_failure():
    client = HttpNotificationClient("http://notification-service:8000")
    with (
        patch("app.notifier.httpx.post", side_effect=httpx.ConnectError("boom")),
        pytest.raises(NotifierError),
    ):
        client.send("https://hooks.example.com/x", {})


# --- HttpIncidentClient --------------------------------------------------------


def _sample_rule() -> AlertRule:
    rule = AlertRule(
        id="rule-1",
        name="high error rate",
        service_name="auth",
        metric_query="up",
        comparison=Comparison.gt,
        threshold=0.05,
        severity=AlertSeverity.critical,
    )
    return rule


def test_incident_client_posts_expected_payload_and_returns_id():
    client = HttpIncidentClient("http://incident-service:8000")
    fake_response = MagicMock(status_code=201, json=lambda: {"id": "incident-42"})
    fake_response.raise_for_status = lambda: None

    with patch("app.incident_client.httpx.post", return_value=fake_response) as mock_post:
        incident_id = client.create_incident_for_alert("alert-1", _sample_rule(), 0.99)

    assert incident_id == "incident-42"
    called_url, called_kwargs = mock_post.call_args
    assert called_url[0] == "http://incident-service:8000/incidents"
    payload = called_kwargs["json"]
    assert payload["service_name"] == "auth"
    assert payload["severity"] == "critical"
    assert payload["source_alert_id"] == "alert-1"


def test_incident_client_raises_on_failure():
    client = HttpIncidentClient("http://incident-service:8000")
    with (
        patch("app.incident_client.httpx.post", side_effect=httpx.ConnectError("boom")),
        pytest.raises(IncidentClientError),
    ):
        client.create_incident_for_alert("alert-1", _sample_rule(), 0.99)
