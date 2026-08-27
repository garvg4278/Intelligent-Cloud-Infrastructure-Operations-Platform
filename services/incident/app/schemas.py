from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import IncidentSeverity, IncidentStatus


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=4000)
    service_name: str = Field(min_length=1, max_length=255)
    severity: IncidentSeverity
    source_alert_id: str | None = None


class IncidentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    message: str
    created_at: datetime


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str | None
    service_name: str
    severity: IncidentSeverity
    status: IncidentStatus
    source_alert_id: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class IncidentDetailOut(IncidentOut):
    events: list[IncidentEventOut] = []


class TransitionRequest(BaseModel):
    status: IncidentStatus


class CommentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
