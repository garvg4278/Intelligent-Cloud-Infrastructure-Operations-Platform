from datetime import datetime, timezone

from sqlalchemy.orm import Session

from . import models, schemas


class InvalidTransitionError(Exception):
    def __init__(self, current: models.IncidentStatus, target: models.IncidentStatus):
        self.current = current
        self.target = target
        super().__init__(f"cannot move from '{current.value}' to '{target.value}'")


def create_incident(db: Session, payload: schemas.IncidentCreate) -> models.Incident:
    incident = models.Incident(
        title=payload.title,
        description=payload.description,
        service_name=payload.service_name,
        severity=payload.severity,
        source_alert_id=payload.source_alert_id,
        status=models.IncidentStatus.open,
    )
    db.add(incident)
    db.flush()
    db.add(
        models.IncidentEvent(
            incident_id=incident.id, event_type="created", message=f"Incident opened: {payload.title}"
        )
    )
    db.commit()
    db.refresh(incident)
    return incident


def get_incident(db: Session, incident_id: str) -> models.Incident | None:
    return db.query(models.Incident).filter(models.Incident.id == incident_id).first()


def get_events(db: Session, incident_id: str) -> list[models.IncidentEvent]:
    return (
        db.query(models.IncidentEvent)
        .filter(models.IncidentEvent.incident_id == incident_id)
        .order_by(models.IncidentEvent.created_at)
        .all()
    )


def list_incidents(
    db: Session,
    status: models.IncidentStatus | None = None,
    service_name: str | None = None,
    severity: models.IncidentSeverity | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[models.Incident]:
    query = db.query(models.Incident)
    if status:
        query = query.filter(models.Incident.status == status)
    if service_name:
        query = query.filter(models.Incident.service_name == service_name)
    if severity:
        query = query.filter(models.Incident.severity == severity)
    return query.order_by(models.Incident.created_at.desc()).offset(offset).limit(limit).all()


def transition_status(
    db: Session, incident: models.Incident, target: models.IncidentStatus
) -> models.Incident:
    allowed = models.ALLOWED_TRANSITIONS[incident.status]
    if target not in allowed:
        raise InvalidTransitionError(incident.status, target)

    previous = incident.status
    incident.status = target
    if target == models.IncidentStatus.resolved:
        incident.resolved_at = datetime.now(timezone.utc)
    elif previous == models.IncidentStatus.resolved and target != models.IncidentStatus.closed:
        incident.resolved_at = None  # reopened

    db.add(incident)
    db.add(
        models.IncidentEvent(
            incident_id=incident.id,
            event_type="status_change",
            message=f"{previous.value} -> {target.value}",
        )
    )
    db.commit()
    db.refresh(incident)
    return incident


def add_comment(db: Session, incident: models.Incident, message: str) -> models.IncidentEvent:
    event = models.IncidentEvent(incident_id=incident.id, event_type="comment", message=message)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
