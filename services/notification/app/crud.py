from datetime import UTC, datetime

from sqlalchemy.orm import Session

from . import models, schemas
from .templating import render


def _utcnow() -> datetime:
    return datetime.now(UTC)


def create_notification(db: Session, payload: schemas.NotificationCreate) -> models.Notification:
    notification = models.Notification(
        channel=payload.channel,
        target=payload.target,
        subject=render(payload.subject, payload.context),
        body=render(payload.body, payload.context),
        max_attempts=payload.max_attempts,
        status=models.NotificationStatus.pending,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def get_notification(db: Session, notification_id: str) -> models.Notification | None:
    return db.query(models.Notification).filter(models.Notification.id == notification_id).first()


def list_notifications(
    db: Session,
    status: models.NotificationStatus | None = None,
    channel: models.NotificationChannel | None = None,
) -> list[models.Notification]:
    query = db.query(models.Notification)
    if status:
        query = query.filter(models.Notification.status == status)
    if channel:
        query = query.filter(models.Notification.channel == channel)
    return query.order_by(models.Notification.created_at.desc()).all()


def record_attempt_failure(db: Session, notification: models.Notification, error: str) -> models.Notification:
    notification.attempts += 1
    notification.last_error = error
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def mark_sent(db: Session, notification: models.Notification) -> models.Notification:
    notification.status = models.NotificationStatus.sent
    notification.sent_at = _utcnow()
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def mark_failed(db: Session, notification: models.Notification, error: str) -> models.Notification:
    notification.status = models.NotificationStatus.failed
    notification.last_error = error
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification
