from unittest.mock import MagicMock, patch

from app.service_clients import HttpAlertClient, HttpDeploymentClient, HttpIncidentClient


def test_deployment_client_returns_full_list_no_cap():
    client = HttpDeploymentClient("http://deployment:8000")
    fake_response = MagicMock(json=lambda: [{"id": str(i)} for i in range(50)])
    fake_response.raise_for_status = lambda: None

    with patch("app.service_clients.httpx.get", return_value=fake_response):
        result = client.all_deployments("auth")

    assert len(result) == 50  # unlike aiops's client, no 5-item cap here


def test_incident_client_queries_by_service_name():
    client = HttpIncidentClient("http://incident:8000")
    fake_response = MagicMock(json=lambda: [{"id": "i1"}])
    fake_response.raise_for_status = lambda: None

    with patch("app.service_clients.httpx.get", return_value=fake_response) as mock_get:
        result = client.all_incidents("auth")

    assert result == [{"id": "i1"}]
    assert mock_get.call_args[1]["params"]["service_name"] == "auth"


def test_alert_client_returns_both_rules_and_filtered_alerts():
    client = HttpAlertClient("http://alert:8000")
    rules_response = MagicMock(json=lambda: [{"id": "r1", "name": "test rule"}])
    rules_response.raise_for_status = lambda: None
    alerts_response = MagicMock(
        json=lambda: [{"id": "a1", "rule_id": "r1"}, {"id": "a2", "rule_id": "other-service-rule"}]
    )
    alerts_response.raise_for_status = lambda: None

    with patch("app.service_clients.httpx.get", side_effect=[rules_response, alerts_response]):
        rules, alerts = client.all_alerts("auth")

    assert rules == [{"id": "r1", "name": "test rule"}]
    assert alerts == [{"id": "a1", "rule_id": "r1"}]
