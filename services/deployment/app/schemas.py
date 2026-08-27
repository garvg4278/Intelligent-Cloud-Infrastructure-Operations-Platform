from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import DeploymentStatus, Environment


class DeploymentCreate(BaseModel):
    service_name: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    environment: Environment
    image_tag: str = Field(min_length=1, max_length=255)


class DeploymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    service_name: str
    environment: Environment
    image_tag: str
    status: DeploymentStatus
    revision: int | None
    error_message: str | None
    is_last_successful: bool
    created_at: datetime
    updated_at: datetime
