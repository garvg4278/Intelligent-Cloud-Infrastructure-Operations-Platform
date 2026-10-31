import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String, Text

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AuditEvent(Base):
    """Deliberately has no updated_at, no soft-delete flag, nothing that
    implies this row is ever mutated after creation -- that's the actual
    enforcement of "immutable history should be preserved" from the
    original design, not just a comment. There is no PUT, PATCH, or
    DELETE route anywhere in this service (see routers/audit.py);
    POST-then-GET is the entire interface.
    """

    __tablename__ = "audit_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor = Column(String(255), nullable=False, index=True)  # user email, or "system"
    action = Column(String(255), nullable=False, index=True)  # e.g. "deployment.created"
    resource_type = Column(String(100), nullable=False, index=True)  # e.g. "deployment"
    resource_id = Column(String(255), nullable=True, index=True)
    source_service = Column(String(100), nullable=False, index=True)  # which service emitted this
    # JSON-encoded text, same reasoning as the aiops service's
    # evidence_json: works identically on SQLite and Postgres without a
    # dialect-specific JSON column type. Either can be absent -- a
    # "created" event has no meaningful before_state, for instance.
    before_state = Column(Text, nullable=True)
    after_state = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)
