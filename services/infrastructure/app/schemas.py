from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .models import EnvironmentStatus, EnvironmentType


class EnvironmentCreate(BaseModel):
    environment_type: EnvironmentType


class EnvironmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    environment_type: EnvironmentType
    status: EnvironmentStatus
    cluster_name: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
