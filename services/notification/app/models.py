import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy import Enum as SAEnum

from .database import Base


class NotificationChannel(str, enum.Enum):
    webhook = "webhook"
    email = "email"


class NotificationStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"  # exhausted max_attempts, or no sender registered for the channel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    channel = Column(SAEnum(NotificationChannel, native_enum=False, length=16), nullable=False, index=True)
    target = Column(String(1000), nullable=False)  # webhook URL or email address
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)  # already rendered -- templating happens before this is stored
    status = Column(
        SAEnum(NotificationStatus, native_enum=False, length=16),
        nullable=False,
        default=NotificationStatus.pending,
        index=True,
    )
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    last_error = Column(String(2000), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
