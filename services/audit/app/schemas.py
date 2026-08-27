from datetime import datetime

from pydantic import BaseModel, Field


class AuditEventCreate(BaseModel):
    actor: str = Field(min_length=1, max_length=255)
    action: str = Field(min_length=1, max_length=255)
    resource_type: str = Field(min_length=1, max_length=100)
    resource_id: str | None = Field(default=None, max_length=255)
    source_service: str = Field(min_length=1, max_length=100)
    before_state: dict | None = None
    after_state: dict | None = None


class AuditEventOut(BaseModel):
    id: str
    actor: str
    action: str
    resource_type: str
    resource_id: str | None
    source_service: str
    before_state: dict | None
    after_state: dict | None
    created_at: datetime
