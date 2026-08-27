import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum

from .database import Base


class IncidentSeverity(str, enum.Enum):
    critical = "critical"
    warning = "warning"
    info = "info"


class IncidentStatus(str, enum.Enum):
    open = "open"
    acknowledged = "acknowledged"
    investigating = "investigating"
    mitigated = "mitigated"
    resolved = "resolved"
    closed = "closed"


# What status an incident can move to from each current status. Enforced in
# crud.transition_status -- not just documentation.
ALLOWED_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.open: {IncidentStatus.acknowledged, IncidentStatus.investigating, IncidentStatus.resolved},
    IncidentStatus.acknowledged: {IncidentStatus.investigating, IncidentStatus.resolved},
    IncidentStatus.investigating: {IncidentStatus.mitigated, IncidentStatus.resolved},
    IncidentStatus.mitigated: {IncidentStatus.resolved},
    IncidentStatus.resolved: {IncidentStatus.closed, IncidentStatus.investigating},  # reopen if it recurs
    IncidentStatus.closed: set(),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(500), nullable=False)
    description = Column(String(4000), nullable=True)
    service_name = Column(String(255), nullable=False, index=True)
    severity = Column(SAEnum(IncidentSeverity, native_enum=False, length=32), nullable=False)
    status = Column(
        SAEnum(IncidentStatus, native_enum=False, length=32),
        nullable=False,
        default=IncidentStatus.open,
        index=True,
    )
    # Alert service's alert id, if this incident was created from one. No
    # real foreign key -- these are two different services' databases (even
    # though they happen to share a Postgres instance today, see the root
    # README's "known simplifications"), so this is just an opaque
    # reference, not an enforced relationship.
    source_alert_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class IncidentEvent(Base):
    """Timeline entries -- both system-recorded status changes and
    human-written comments, in one ordered feed."""

    __tablename__ = "incident_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    incident_id = Column(String(36), ForeignKey("incidents.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # "status_change" | "comment" | "created"
    message = Column(String(2000), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
