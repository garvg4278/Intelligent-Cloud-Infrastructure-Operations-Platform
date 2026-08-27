"""Records an audit event by calling the audit service. A failure here
must NEVER break the caller's actual operation -- a login succeeding
can't depend on the audit service being up. Every call site wraps this
in try/except and logs on failure rather than letting it propagate; see
record_safely() below, which is what call sites should actually use.
"""

import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

SOURCE_SERVICE = "auth"


class AuditClientError(Exception):
    pass


class AuditClient(Protocol):
    def record(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str | None,
        before_state: dict | None = None,
        after_state: dict | None = None,
    ) -> None: ...


class HttpAuditClient:
    def __init__(self, base_url: str, source_service: str):
        self.base_url = base_url
        self.source_service = source_service

    def record(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str | None,
        before_state: dict | None = None,
        after_state: dict | None = None,
    ) -> None:
        try:
            resp = httpx.post(
                f"{self.base_url}/audit/events",
                json={
                    "actor": actor,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "source_service": self.source_service,
                    "before_state": before_state,
                    "after_state": after_state,
                },
                timeout=10,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise AuditClientError(f"audit service call failed: {exc}") from exc


_audit_client: AuditClient | None = None


def get_audit_client() -> AuditClient:
    global _audit_client
    if _audit_client is None:
        from .config import settings

        _audit_client = HttpAuditClient(settings.AUDIT_SERVICE_URL, SOURCE_SERVICE)
    return _audit_client


def set_audit_client(client: AuditClient | None) -> None:
    """Test hook."""
    global _audit_client
    _audit_client = client


def record_safely(
    actor: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    before_state: dict | None = None,
    after_state: dict | None = None,
) -> None:
    """What call sites actually use -- catches AuditClientError and logs
    it rather than letting it propagate. The audit trail having a gap is
    a real problem worth logging loudly; it is never a reason to fail the
    request that triggered it.
    """
    try:
        get_audit_client().record(actor, action, resource_type, resource_id, before_state, after_state)
    except AuditClientError:
        logger.exception("audit event recording failed: action=%s resource_id=%s", action, resource_id)
