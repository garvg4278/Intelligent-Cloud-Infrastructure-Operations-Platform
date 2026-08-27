from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..database import get_db
from ..models import NotificationChannel, NotificationStatus
from ..tasks import deliver_notification_task

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("", response_model=schemas.NotificationOut, status_code=status.HTTP_202_ACCEPTED)
def create_notification(payload: schemas.NotificationCreate, db: Session = Depends(get_db)):
    notification = crud.create_notification(db, payload)
    deliver_notification_task.delay(notification.id)
    db.refresh(notification)
    return notification


@router.get("", response_model=list[schemas.NotificationOut])
def list_notifications(
    status_filter: NotificationStatus | None = None,
    channel: NotificationChannel | None = None,
    db: Session = Depends(get_db),
):
    return crud.list_notifications(db, status=status_filter, channel=channel)


@router.get("/{notification_id}", response_model=schemas.NotificationOut)
def get_notification(notification_id: str, db: Session = Depends(get_db)):
    notification = crud.get_notification(db, notification_id)
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="notification not found")
    return notification
