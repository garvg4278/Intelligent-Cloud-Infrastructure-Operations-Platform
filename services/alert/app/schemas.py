from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import AlertSeverity, AlertStatus, Comparison


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    service_name: str = Field(min_length=1, max_length=255)
    metric_query: str = Field(min_length=1, max_length=1000)
    comparison: Comparison
    threshold: float
    severity: AlertSeverity
    webhook_url: str | None = None
    is_active: bool = True


class AlertRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    service_name: str
    metric_query: str
    comparison: Comparison
    threshold: float
    severity: AlertSeverity
    webhook_url: str | None
    is_active: bool
    created_at: datetime


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rule_id: str
    status: AlertStatus
    severity: AlertSeverity
    message: str
    observed_value: float
    acknowledged_at: datetime | None
    fired_at: datetime
    resolved_at: datetime | None
    incident_id: str | None
