"""Unit test for HttpAuditClient's request construction, underlying httpx
call mocked -- same pattern as every other adapter test in this repo.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.audit_client import AuditClientError, HttpAuditClient


def test_records_event_with_correct_shape():
    client = HttpAuditClient("http://audit-service:8000", source_service="auth")
    fake_response = MagicMock(status_code=201)
    fake_response.raise_for_status = lambda: None

    with patch("app.audit_client.httpx.post", return_value=fake_response) as mock_post:
        client.record(
            actor="alice@example.com",
            action="user.login",
            resource_type="user",
            resource_id="user-123",
        )

    called_url, called_kwargs = mock_post.call_args
    assert called_url[0] == "http://audit-service:8000/audit/events"
    body = called_kwargs["json"]
    assert body["actor"] == "alice@example.com"
    assert body["action"] == "user.login"
    assert body["source_service"] == "auth"
    assert body["before_state"] is None
    assert body["after_state"] is None


def test_records_event_with_before_after_state():
    client = HttpAuditClient("http://audit-service:8000", source_service="auth")
    fake_response = MagicMock(status_code=201)
    fake_response.raise_for_status = lambda: None

    with patch("app.audit_client.httpx.post", return_value=fake_response) as mock_post:
        client.record(
            actor="alice@example.com", action="user.registered", resource_type="user",
            resource_id="user-123", after_state={"role": "viewer"},
        )

    assert mock_post.call_args[1]["json"]["after_state"] == {"role": "viewer"}


def test_raises_audit_client_error_on_failure():
    client = HttpAuditClient("http://audit-service:8000", source_service="auth")
    with (
        patch("app.audit_client.httpx.post", side_effect=httpx.ConnectError("boom")),
        pytest.raises(AuditClientError),
    ):
        client.record(actor="x", action="y", resource_type="z", resource_id=None)
