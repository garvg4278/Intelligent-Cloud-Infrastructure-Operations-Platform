from celery import Celery

from .config import settings
from .executor import deliver_with_retries
from .sender import get_sender_registry

celery_app = Celery("icop_notification", broker=settings.CELERY_BROKER_URL)
celery_app.conf.update(task_ignore_result=True, task_default_queue="notifications")


@celery_app.task(name="notification.deliver")
def deliver_notification_task(notification_id: str) -> None:
    deliver_with_retries(notification_id, get_sender_registry())
