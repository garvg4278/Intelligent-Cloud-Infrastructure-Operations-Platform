import json

from sqlalchemy.orm import Session

from . import models, schemas


def create_event(db: Session, payload: schemas.AuditEventCreate) -> models.AuditEvent:
    event = models.AuditEvent(
        actor=payload.actor,
        action=payload.action,
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        source_service=payload.source_service,
        before_state=json.dumps(payload.before_state) if payload.before_state is not None else None,
        after_state=json.dumps(payload.after_state) if payload.after_state is not None else None,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_event(db: Session, event_id: str) -> models.AuditEvent | None:
    return db.query(models.AuditEvent).filter(models.AuditEvent.id == event_id).first()


def list_events(
    db: Session,
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    source_service: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[models.AuditEvent]:
    query = db.query(models.AuditEvent)
    if actor:
        query = query.filter(models.AuditEvent.actor == actor)
    if action:
        query = query.filter(models.AuditEvent.action == action)
    if resource_type:
        query = query.filter(models.AuditEvent.resource_type == resource_type)
    if source_service:
        query = query.filter(models.AuditEvent.source_service == source_service)
    return query.order_by(models.AuditEvent.created_at.desc()).offset(offset).limit(limit).all()


def to_out(event: models.AuditEvent) -> schemas.AuditEventOut:
    return schemas.AuditEventOut(
        id=event.id,
        actor=event.actor,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        source_service=event.source_service,
        before_state=json.loads(event.before_state) if event.before_state is not None else None,
        after_state=json.loads(event.after_state) if event.after_state is not None else None,
        created_at=event.created_at,
    )
