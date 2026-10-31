"""Two real delivery channels. Webhook needs no configuration and is
always registered; email needs real SMTP credentials and is only
registered if SMTP_HOST is set -- same bring-your-own-infra shape as
every other external integration in this repo.
"""

from __future__ import annotations

import ipaddress
import smtplib
import socket
import ssl
from email.errors import MessageError
from email.mime.text import MIMEText
from typing import Protocol
from urllib.parse import urlsplit

import httpx


class SenderError(Exception):
    pass


class Sender(Protocol):
    def send(self, target: str, subject: str, body: str) -> None: ...


def check_webhook_target(target: str, resolver=socket.getaddrinfo, allow_private: bool = False) -> None:
    """Refuse webhook targets that would turn this service into a proxy into
    the private network (SSRF). Webhook URLs are caller-supplied, and this
    process runs inside the cluster/VPC: without this check anyone who can
    queue a notification could aim it at the cloud metadata endpoint
    (169.254.169.254 -> instance-role credentials), at Redis/RabbitMQ/
    Postgres, or at another service's unauthenticated internal API -- and
    read the error text back from the stored `last_error`.

    Every address the host resolves to must be globally routable. Known
    residual risk: DNS can answer differently between this check and the
    connection (rebinding). Closing that fully means pinning the connection
    to the checked IP; egress NetworkPolicy/security groups are the
    defence-in-depth for it (see ROADMAP.md).
    """
    parts = urlsplit(target)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise SenderError("webhook target must be an http(s) URL with a host")
    if parts.username or parts.password:
        raise SenderError("webhook target must not embed credentials")
    if allow_private:
        return
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
        infos = resolver(parts.hostname, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise SenderError(f"webhook host could not be resolved: {exc}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        ip = getattr(ip, "ipv4_mapped", None) or ip  # ::ffff:127.0.0.1 is loopback, not "IPv6"
        if not ip.is_global:
            raise SenderError("webhook target resolves to a non-public address")


class WebhookSender:
    def __init__(self, resolver=socket.getaddrinfo, allow_private: bool = False):
        self._resolver = resolver
        self._allow_private = allow_private

    def send(self, target: str, subject: str, body: str) -> None:
        check_webhook_target(target, self._resolver, self._allow_private)
        try:
            # No redirects: a public host answering 302 -> http://169.254...
            # would walk straight around the address check above.
            resp = httpx.post(
                target, json={"subject": subject, "body": body}, timeout=10, follow_redirects=False
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise SenderError(f"webhook delivery failed: {exc}") from exc


class SMTPEmailSender:
    def __init__(self, host: str, port: int, username: str, password: str, from_address: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_address = from_address

    def send(self, target: str, subject: str, body: str) -> None:
        message = MIMEText(body)
        message["Subject"] = subject
        message["From"] = self.from_address
        message["To"] = target

        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                # Explicit context: verifies the server certificate and hostname.
                # (smtplib's no-argument default is an unverified context, which
                # makes STARTTLS encryption without authentication.)
                server.starttls(context=ssl.create_default_context())
                if self.username:
                    server.login(self.username, self.password)
                server.sendmail(self.from_address, [target], message.as_string())
        except (smtplib.SMTPException, OSError, MessageError) as exc:
            raise SenderError(f"email delivery failed: {exc}") from exc


_sender_registry: dict[str, Sender] | None = None


def get_sender_registry() -> dict[str, Sender]:
    global _sender_registry
    if _sender_registry is None:
        from .config import settings

        registry: dict[str, Sender] = {
            "webhook": WebhookSender(allow_private=settings.WEBHOOK_ALLOW_PRIVATE_TARGETS)
        }
        if settings.SMTP_HOST:
            registry["email"] = SMTPEmailSender(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                settings.SMTP_USERNAME,
                settings.SMTP_PASSWORD,
                settings.SMTP_FROM_ADDRESS,
            )
        _sender_registry = registry
    return _sender_registry


def set_sender_registry(registry: dict[str, Sender] | None) -> None:
    """Test hook."""
    global _sender_registry
    _sender_registry = registry
