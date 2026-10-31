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


def _paged_get(total: int, page_size: int = 200):
    """Fake httpx.get that behaves like the real list endpoints: honours
    limit/offset (capped at 200) over `total` rows, newest first."""
    rows = [{"id": str(i), "rule_id": "r1"} for i in range(total)]
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(dict(params or {}))
        limit = min(int(params.get("limit", 50)), 200)  # the real endpoints default to 50, cap at 200
        offset = int(params.get("offset", 0))
        response = MagicMock(json=lambda: rows[offset : offset + limit])
        response.raise_for_status = lambda: None
        return response

    return fake_get, calls


def test_deployment_client_pages_through_more_than_one_page_of_history():
    """Regression: with 450 deployments the client used to see 50 and
    report statistics from them without any error."""
    fake_get, calls = _paged_get(450)
    with patch("app.service_clients.httpx.get", side_effect=fake_get):
        result = HttpDeploymentClient("http://deployment:8000").all_deployments("auth")

    assert len(result) == 450
    assert len({r["id"] for r in result}) == 450  # no duplicates across page boundaries
    assert [c["offset"] for c in calls] == [0, 200, 400]
    assert all(c["service_name"] == "auth" and c["limit"] == 200 for c in calls)


def test_exact_multiple_of_page_size_terminates_cleanly():
    fake_get, calls = _paged_get(400)
    with patch("app.service_clients.httpx.get", side_effect=fake_get):
        result = HttpIncidentClient("http://incident:8000").all_incidents("auth")
    assert len(result) == 400
    assert len(calls) == 3  # third (empty) page is what proves there is nothing more


def test_alert_client_pages_and_asks_the_server_to_filter_by_service():
    rules = MagicMock(json=lambda: [{"id": "r1"}])
    rules.raise_for_status = lambda: None
    fake_get, calls = _paged_get(250)

    def router(url, params=None, timeout=None):
        return rules if url.endswith("/alerts/rules") else fake_get(url, params=params, timeout=timeout)

    with patch("app.service_clients.httpx.get", side_effect=router):
        _, alerts = HttpAlertClient("http://alert:8000").all_alerts("auth")

    assert len(alerts) == 250
    assert all(c.get("service_name") == "auth" for c in calls)


def test_runaway_dataset_is_an_error_not_a_silently_truncated_statistic():
    import pytest

    from app.service_clients import MAX_PAGES, PAGE_SIZE, ServiceClientError

    fake_get, _ = _paged_get(MAX_PAGES * PAGE_SIZE + 1)
    with (
        patch("app.service_clients.httpx.get", side_effect=fake_get),
        pytest.raises(ServiceClientError, match="truncated"),
    ):
        HttpDeploymentClient("http://deployment:8000").all_deployments("auth")
