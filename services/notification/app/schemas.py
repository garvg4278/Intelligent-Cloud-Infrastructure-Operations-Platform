from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import NotificationChannel, NotificationStatus


class NotificationCreate(BaseModel):
    channel: NotificationChannel
    target: str = Field(min_length=1, max_length=1000)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)
    # Flat key -> value substitutions for {{key}} placeholders in subject/body.
    context: dict[str, str] = {}
    max_attempts: int = Field(default=3, ge=1, le=10)

    @field_validator("target", "subject")
    @classmethod
    def _no_header_injection(cls, value: str) -> str:
        # These become SMTP headers (To:/Subject:). A CR/LF lets a caller add
        # their own headers (Bcc: ...) -- and Python's MIME layer refuses to
        # serialise such a message, which used to leave the notification
        # stuck in "pending" forever instead of failing.
        if "\r" in value or "\n" in value:
            raise ValueError("must not contain line breaks")
        return value


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
