"""Delivers a firing alert via the notification service instead of
sending a webhook directly -- per the original design's explicit
principle ("notifications are async and failure-prone... should not be
mixed into business logic"), delivery, retries, and tracking now live in
one place (services/notification) instead of being duplicated here.

The Notifier protocol's shape (send(webhook_url, payload)) is unchanged
on purpose: executor.py, which calls this, needed zero changes to switch
implementations -- only what get_notifier() returns by default.
"""

import json
from typing import Protocol

import httpx


class NotifierError(Exception):
    pass


class Notifier(Protocol):
    def send(self, webhook_url: str, payload: dict) -> None: ...


class HttpNotificationClient:
    """Real implementation: POSTs to the notification service's
    /notifications endpoint (channel="webhook", target=webhook_url)
    rather than delivering to webhook_url directly. The notification
    service owns retries and delivery tracking from here.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url

    def send(self, webhook_url: str, payload: dict) -> None:
        severity = payload.get("severity", "unknown").upper()
        rule_name = payload.get("rule_name", "unknown rule")
        service_name = payload.get("service_name", "unknown service")
        subject = f"[{severity}] {rule_name} ({service_name})"
        # payload["message"] is already a fully-formed, human-readable
        # string from the alert's own creation (see crud.create_alert) --
        # used as-is rather than re-templated. The full structured
        # payload still goes along as JSON in case a receiver wants it.
        body = payload.get("message") or json.dumps(payload)

        try:
            resp = httpx.post(
                f"{self.base_url}/notifications",
                json={"channel": "webhook", "target": webhook_url, "subject": subject, "body": body},
                timeout=10,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotifierError(f"notification service call failed: {exc}") from exc


_notifier: Notifier | None = None


def get_notifier() -> Notifier:
    global _notifier
    if _notifier is None:
        from .config import settings

        _notifier = HttpNotificationClient(settings.NOTIFICATION_SERVICE_URL)
    return _notifier


def set_notifier(notifier: Notifier | None) -> None:
    """Test hook."""
    global _notifier
    _notifier = notifier
