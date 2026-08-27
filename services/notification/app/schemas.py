from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import NotificationChannel, NotificationStatus


class NotificationCreate(BaseModel):
    channel: NotificationChannel
    target: str = Field(min_length=1, max_length=1000)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)
    # Flat key -> value substitutions for {{key}} placeholders in subject/body.
    context: dict[str, str] = {}
    max_attempts: int = Field(default=3, ge=1, le=10)


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    channel: NotificationChannel
    target: str
    subject: str
    body: str
    status: NotificationStatus
    attempts: int
    max_attempts: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None
