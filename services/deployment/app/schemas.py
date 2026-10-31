from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import DeploymentStatus, Environment


class DeploymentCreate(BaseModel):
    service_name: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    environment: Environment
    # OCI image-tag grammar: [A-Za-z0-9_][A-Za-z0-9_.-]{0,127}. The value is
    # handed to Helm, and before this pattern existed a tag such as
    # "v1,image.repository=evil/miner,serviceAccount.name=privileged" was
    # accepted and turned into extra `--set` assignments -- letting an API
    # caller override which image runs. Nothing outside the grammar is a
    # legitimate tag, so reject rather than escape.
    image_tag: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


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
