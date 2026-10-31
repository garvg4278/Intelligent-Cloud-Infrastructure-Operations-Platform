import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy import Enum as SAEnum

from .database import Base


class Environment(str, enum.Enum):
    local = "local"
    staging = "staging"
    production = "production"


class DeploymentStatus(str, enum.Enum):
    pending = "pending"
    deploying = "deploying"
    health_checking = "health_checking"
    succeeded = "succeeded"
    rolling_back = "rolling_back"
    rolled_back = "rolled_back"
    failed = "failed"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    service_name = Column(String(255), nullable=False, index=True)
    environment = Column(SAEnum(Environment, native_enum=False, length=32), nullable=False, index=True)
    image_tag = Column(String(255), nullable=False)
    status = Column(
        SAEnum(DeploymentStatus, native_enum=False, length=32),
        nullable=False,
        default=DeploymentStatus.pending,
        index=True,
    )
    revision = Column(Integer, nullable=True)
    error_message = Column(String(2000), nullable=True)
    # Fast lookup for "what's the last release that passed its health check"
    # -- that's the rollback target when a later deploy fails.
    is_last_successful = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
