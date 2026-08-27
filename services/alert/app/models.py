import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, String
from sqlalchemy import Enum as SAEnum

from .database import Base


class AlertSeverity(str, enum.Enum):
    critical = "critical"
    warning = "warning"
    info = "info"


class Comparison(str, enum.Enum):
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"


class AlertStatus(str, enum.Enum):
    firing = "firing"
    resolved = "resolved"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    service_name = Column(String(255), nullable=False, index=True)
    # Raw PromQL, e.g. 'rate(http_requests_total{status=~"5.."}[5m])'
    metric_query = Column(String(1000), nullable=False)
    comparison = Column(SAEnum(Comparison, native_enum=False, length=16), nullable=False)
    threshold = Column(Float, nullable=False)
    severity = Column(SAEnum(AlertSeverity, native_enum=False, length=32), nullable=False)
    # No webhook_url -> alert still fires and is recorded, just nothing is
    # notified. Not every rule needs a channel.
    webhook_url = Column(String(1000), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_id = Column(String(36), ForeignKey("alert_rules.id"), nullable=False, index=True)
    status = Column(
        SAEnum(AlertStatus, native_enum=False, length=16),
        nullable=False,
        default=AlertStatus.firing,
        index=True,
    )
    # copied at fire time, so a later rule edit doesn't rewrite history
    severity = Column(SAEnum(AlertSeverity, native_enum=False, length=32), nullable=False)
    message = Column(String(1000), nullable=False)
    observed_value = Column(Float, nullable=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    fired_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    # Opaque reference to the incident service's Incident.id -- see that
    # service's README for why this isn't a real foreign key.
    incident_id = Column(String(36), nullable=True)
