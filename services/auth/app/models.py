import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy import Enum as SAEnum

from .database import Base


class Role(str, enum.Enum):
    admin = "admin"
    operator = "operator"
    developer = "developer"
    viewer = "viewer"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    # String(36) rather than a Postgres-native UUID column so the same
    # model works unmodified against SQLite in tests and Postgres in
    # production without a dialect-specific type.
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    # native_enum=False -> stored as VARCHAR + CHECK constraint instead of a
    # Postgres ENUM type, so adding a role later doesn't require an
    # ALTER TYPE migration. Worth revisiting once Alembic is in place.
    role = Column(SAEnum(Role, native_enum=False, length=32), nullable=False, default=Role.viewer)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
