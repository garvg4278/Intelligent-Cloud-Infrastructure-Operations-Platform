"""Unit tests for the two real Sender implementations. WebhookSender is
mocked at httpx same as every other adapter test in this repo.
SMTPEmailSender is mocked at smtplib.SMTP -- no real mail server
available, so this checks that MY code correctly opens a connection,
starts TLS, authenticates, and calls sendmail with the right envelope,
not that a real inbox receives anything.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.sender import SenderError, SMTPEmailSender, WebhookSender


def test_webhook_sender_posts_subject_and_body():
    sender = WebhookSender()
    fake_response = MagicMock(status_code=200)
    fake_response.raise_for_status = lambda: None

    with patch("app.sender.httpx.post", return_value=fake_response) as mock_post:
        sender.send("https://hooks.example.com/x", "Subject", "Body")

    called_url, called_kwargs = mock_post.call_args
    assert called_url[0] == "https://hooks.example.com/x"
    assert called_kwargs["json"] == {"subject": "Subject", "body": "Body"}


def test_webhook_sender_raises_sender_error_on_failure():
    sender = WebhookSender()
    with (
        patch("app.sender.httpx.post", side_effect=httpx.ConnectError("boom")),
        pytest.raises(SenderError),
    ):
        sender.send("https://hooks.example.com/x", "s", "b")


def test_smtp_sender_sends_via_starttls_with_login():
    sender = SMTPEmailSender(
        host="smtp.example.com", port=587, username="user", password="pass", from_address="icop@example.com"
    )
    mock_smtp_instance = MagicMock()
    mock_smtp_cm = MagicMock()
    mock_smtp_cm.__enter__ = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_cm.__exit__ = MagicMock(return_value=False)

    with patch("app.sender.smtplib.SMTP", return_value=mock_smtp_cm) as mock_smtp_cls:
        sender.send("someone@example.com", "Subject", "Body text")

    mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=10)
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_instance.login.assert_called_once_with("user", "pass")
    assert mock_smtp_instance.sendmail.call_count == 1
    from_addr, to_addrs, message_text = mock_smtp_instance.sendmail.call_args[0]
    assert from_addr == "icop@example.com"
    assert to_addrs == ["someone@example.com"]
    assert "Subject: Subject" in message_text
    assert "Body text" in message_text


def test_smtp_sender_skips_login_when_no_username_configured():
    sender = SMTPEmailSender(
        host="smtp.example.com", port=587, username="", password="", from_address="icop@example.com"
    )
    mock_smtp_instance = MagicMock()
    mock_smtp_cm = MagicMock()
    mock_smtp_cm.__enter__ = MagicMock(return_value=mock_smtp_instance)
    mock_smtp_cm.__exit__ = MagicMock(return_value=False)

    with patch("app.sender.smtplib.SMTP", return_value=mock_smtp_cm):
        sender.send("someone@example.com", "s", "b")

    mock_smtp_instance.login.assert_not_called()


def test_smtp_sender_raises_sender_error_on_connection_failure():
    sender = SMTPEmailSender(
        host="smtp.example.com", port=587, username="", password="", from_address="icop@example.com"
    )
    with (
        patch("app.sender.smtplib.SMTP", side_effect=OSError("connection refused")),
        pytest.raises(SenderError),
    ):
        sender.send("someone@example.com", "s", "b")


def test_sender_registry_only_includes_email_when_smtp_host_configured():
    from app.sender import get_sender_registry, set_sender_registry

    set_sender_registry(None)
    with patch("app.config.settings.SMTP_HOST", ""):
        registry = get_sender_registry()
    assert "webhook" in registry
    assert "email" not in registry
    set_sender_registry(None)


def test_sender_registry_includes_email_when_smtp_host_is_configured():
    from app.sender import get_sender_registry, set_sender_registry

    set_sender_registry(None)
    with patch("app.config.settings.SMTP_HOST", "smtp.example.com"):
        registry = get_sender_registry()
    assert "webhook" in registry
    assert "email" in registry
    set_sender_registry(None)
