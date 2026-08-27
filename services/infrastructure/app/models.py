import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlalchemy import Enum as SAEnum

from .database import Base


class EnvironmentType(str, enum.Enum):
    staging = "staging"
    production = "production"


class EnvironmentStatus(str, enum.Enum):
    pending = "pending"
    provisioning_infra = "provisioning_infra"  # terraform apply running
    configuring_nodes = "configuring_nodes"  # ansible playbook running
    ready = "ready"
    provision_failed = "provision_failed"
    destroying = "destroying"
    destroyed = "destroyed"
    destroy_failed = "destroy_failed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Environment(Base):
    """One row per provision/destroy lifecycle of one of this repo's two
    real Terraform environments (terraform/environments/{staging,production}
    -- see that directory's README for why there are exactly two, not an
    arbitrary number). `name` is derived from the environment type and its
    lifecycle ID (see crud.create_environment), never user-supplied. This
    retains the record of a destroyed lifecycle while allowing that target
    to be provisioned again.
    """

    __tablename__ = "environments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True, index=True)
    environment_type = Column(SAEnum(EnvironmentType, native_enum=False, length=32), nullable=False, index=True)
    status = Column(
        SAEnum(EnvironmentStatus, native_enum=False, length=32),
        nullable=False,
        default=EnvironmentStatus.pending,
        index=True,
    )
    # Populated from `terraform output` once provisioning_infra succeeds --
    # see terraform/environments/*/outputs.tf's cluster_name output.
    cluster_name = Column(String(255), nullable=True)
    error_message = Column(String(2000), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
