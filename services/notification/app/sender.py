"""Two real delivery channels. Webhook needs no configuration and is
always registered; email needs real SMTP credentials and is only
registered if SMTP_HOST is set -- same bring-your-own-infra shape as
every other external integration in this repo.
"""

from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from typing import Protocol

import httpx


class SenderError(Exception):
    pass


class Sender(Protocol):
    def send(self, target: str, subject: str, body: str) -> None: ...


class WebhookSender:
    def send(self, target: str, subject: str, body: str) -> None:
        try:
            resp = httpx.post(target, json={"subject": subject, "body": body}, timeout=10)
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
                server.starttls()
                if self.username:
                    server.login(self.username, self.password)
                server.sendmail(self.from_address, [target], message.as_string())
        except (smtplib.SMTPException, OSError) as exc:
            raise SenderError(f"email delivery failed: {exc}") from exc


_sender_registry: dict[str, Sender] | None = None


def get_sender_registry() -> dict[str, Sender]:
    global _sender_registry
    if _sender_registry is None:
        from .config import settings

        registry: dict[str, Sender] = {"webhook": WebhookSender()}
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
