from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.service_clients import (
    HttpAlertClient,
    HttpDeploymentClient,
    HttpIncidentClient,
    PrometheusClient,
    ServiceClientError,
)


def test_deployment_client_queries_by_service_name_and_caps_at_five():
    client = HttpDeploymentClient("http://deployment:8000")
    fake_response = MagicMock(json=lambda: [{"id": str(i)} for i in range(10)])
    fake_response.raise_for_status = lambda: None

    with patch("app.service_clients.httpx.get", return_value=fake_response) as mock_get:
        result = client.recent_deployments("auth")

    assert len(result) == 5
    called_url, called_kwargs = mock_get.call_args
    assert called_url[0] == "http://deployment:8000/deployments"
    assert called_kwargs["params"]["service_name"] == "auth"


def test_deployment_client_raises_service_client_error_on_failure():
    client = HttpDeploymentClient("http://deployment:8000")
    with (
        patch("app.service_clients.httpx.get", side_effect=httpx.ConnectError("boom")),
        pytest.raises(ServiceClientError),
    ):
        client.recent_deployments("auth")


def test_alert_client_joins_rules_and_alerts_by_rule_id():
    client = HttpAlertClient("http://alert:8000")
    rules_response = MagicMock(json=lambda: [{"id": "rule-1"}, {"id": "rule-2"}])
    rules_response.raise_for_status = lambda: None
    alerts_response = MagicMock(
        json=lambda: [
            {"id": "a1", "rule_id": "rule-1"},
            {"id": "a2", "rule_id": "rule-999"},  # belongs to a different service's rule
        ]
    )
    alerts_response.raise_for_status = lambda: None

    with patch("app.service_clients.httpx.get", side_effect=[rules_response, alerts_response]):
        result = client.recent_alerts("auth")

    assert len(result) == 1
    assert result[0]["id"] == "a1"


def test_incident_client_queries_by_service_name():
    client = HttpIncidentClient("http://incident:8000")
    fake_response = MagicMock(json=lambda: [{"id": "i1"}])
    fake_response.raise_for_status = lambda: None

    with patch("app.service_clients.httpx.get", return_value=fake_response) as mock_get:
        result = client.recent_incidents("auth")

    assert result == [{"id": "i1"}]
    assert mock_get.call_args[1]["params"]["service_name"] == "auth"


def test_prometheus_client_parses_instant_query_result():
    client = PrometheusClient("http://prometheus:9090")
    fake_response = MagicMock(
        json=lambda: {"status": "success", "data": {"result": [{"value": [1700000000, "0.05"]}]}}
    )
    fake_response.raise_for_status = lambda: None

    with patch("app.service_clients.httpx.get", return_value=fake_response):
        value = client.query("up")

    assert value == 0.05


def test_prometheus_client_raises_on_empty_result():
    client = PrometheusClient("http://prometheus:9090")
    fake_response = MagicMock(json=lambda: {"status": "success", "data": {"result": []}})
    fake_response.raise_for_status = lambda: None

    with (
        patch("app.service_clients.httpx.get", return_value=fake_response),
        pytest.raises(ServiceClientError, match="no data"),
    ):
        client.query("nonexistent_metric")
