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

from app.sender import SenderError, SMTPEmailSender, WebhookSender, check_webhook_target


def _resolver_for(*addresses):
    """Stand-in for socket.getaddrinfo -- no real DNS in unit tests."""
    return lambda host, port, proto=0: [(2, 1, 6, "", (addr, port)) for addr in addresses]


PUBLIC = _resolver_for("93.184.216.34")


def test_webhook_sender_posts_subject_and_body():
    sender = WebhookSender(resolver=PUBLIC)
    fake_response = MagicMock(status_code=200)
    fake_response.raise_for_status = lambda: None

    with patch("app.sender.httpx.post", return_value=fake_response) as mock_post:
        sender.send("https://hooks.example.com/x", "Subject", "Body")

    called_url, called_kwargs = mock_post.call_args
    assert called_url[0] == "https://hooks.example.com/x"
    assert called_kwargs["json"] == {"subject": "Subject", "body": "Body"}


def test_webhook_sender_raises_sender_error_on_failure():
    sender = WebhookSender(resolver=PUBLIC)
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


# ---- SSRF ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "address",
    [
        "169.254.169.254",   # cloud metadata endpoint -> instance-role credentials
        "127.0.0.1",
        "10.0.3.7",          # in-VPC: Postgres / Redis / other services
        "172.16.0.5",
        "192.168.1.1",
        "100.64.0.1",        # carrier-grade NAT, not "public" either
        "0.0.0.0",
        "::1",
        "fe80::1",
        "::ffff:127.0.0.1",  # IPv4-mapped loopback must not slip through as 'IPv6'
        "fd00::1",
    ],
)
def test_webhook_target_resolving_to_a_non_public_address_is_refused(address):
    with pytest.raises(SenderError, match="non-public"):
        check_webhook_target("https://anything.example.com/hook", resolver=_resolver_for(address))


def test_one_private_answer_among_public_ones_is_enough_to_refuse():
    with pytest.raises(SenderError, match="non-public"):
        check_webhook_target("https://x.example.com", resolver=_resolver_for("93.184.216.34", "10.0.0.9"))


@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://x", "ftp://x/y", "http://", "not a url", "https://user:pw@x.example.com"])
def test_non_http_or_credentialed_targets_are_refused(url):
    with pytest.raises(SenderError):
        check_webhook_target(url, resolver=PUBLIC)


def test_public_target_is_allowed():
    check_webhook_target("https://hooks.example.com/x", resolver=PUBLIC)


def test_allow_private_switch_permits_an_internal_receiver():
    check_webhook_target(
        "http://chat-bridge.svc:8080/hook", resolver=_resolver_for("10.1.2.3"), allow_private=True
    )


def test_unresolvable_host_is_a_sender_error_not_a_crash():
    def nxdomain(host, port, proto=0):
        raise OSError("Name or service not known")

    with pytest.raises(SenderError, match="could not be resolved"):
        check_webhook_target("https://nope.invalid", resolver=nxdomain)


def test_private_target_never_reaches_httpx():
    with patch("app.sender.httpx.post") as mock_post, pytest.raises(SenderError):
        WebhookSender(resolver=_resolver_for("169.254.169.254")).send("http://metadata/latest", "s", "b")
    mock_post.assert_not_called()


def test_webhook_does_not_follow_redirects():
    fake = MagicMock()
    fake.raise_for_status = lambda: None
    with patch("app.sender.httpx.post", return_value=fake) as mock_post:
        WebhookSender(resolver=PUBLIC).send("https://hooks.example.com/x", "s", "b")
    assert mock_post.call_args[1]["follow_redirects"] is False


# ---- SMTP --------------------------------------------------------------------------------

def test_starttls_uses_a_verifying_context():
    import ssl

    sender = SMTPEmailSender("smtp.example.com", 587, "", "", "icop@example.com")
    instance = MagicMock()
    cm = MagicMock(__enter__=MagicMock(return_value=instance), __exit__=MagicMock(return_value=False))
    with patch("app.sender.smtplib.SMTP", return_value=cm):
        sender.send("a@example.com", "s", "b")
    context = instance.starttls.call_args[1]["context"]
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_header_injection_that_reaches_the_sender_is_a_sender_error():
    sender = SMTPEmailSender("smtp.example.com", 587, "", "", "icop@example.com")
    with (
        patch("app.sender.smtplib.SMTP", return_value=MagicMock()),
        pytest.raises(SenderError, match="email delivery failed"),
    ):
        sender.send("a@b.test", "hello\nBcc: victim@example.com", "b")
