"""Delivery with retries -- all within one call, using dependency-injected
sleep so tests run instantly instead of actually waiting through backoff.
Deliberately NOT using Celery's own retry/countdown machinery: this repo
already relies on Celery's *eager* mode for testing everywhere else, and
eager mode's interaction with self.retry() is a real subtlety that would
need its own verification to trust -- a synchronous retry loop with
injectable time is simpler to reason about and just as real a pattern
(plenty of production code retries exactly this way instead of re-queuing
through a broker for every attempt).
"""

import logging
import time

from . import crud, models
from .database import get_db_session
from .sender import Sender, SenderError

logger = logging.getLogger(__name__)


def deliver_with_retries(
    notification_id: str,
    sender_registry: dict[str, Sender],
    sleep_fn=time.sleep,
) -> None:
    with get_db_session() as db:
        notification = crud.get_notification(db, notification_id)
        if notification is None:
            logger.warning("notification %s not found, nothing to deliver", notification_id)
            return
        if notification.status == models.NotificationStatus.sent:
            return
        max_attempts = notification.max_attempts
        channel = notification.channel

    sender = sender_registry.get(channel)
    if sender is None:
        with get_db_session() as db:
            notification = crud.get_notification(db, notification_id)
            crud.mark_failed(db, notification, f"no sender registered for channel '{channel}'")
        return

    for attempt_number in range(1, max_attempts + 1):
        with get_db_session() as db:
            notification = crud.get_notification(db, notification_id)
            try:
                sender.send(notification.target, notification.subject, notification.body)
                crud.mark_sent(db, notification)
                return
            except SenderError as exc:
                crud.record_attempt_failure(db, notification, str(exc))

        if attempt_number < max_attempts:
            sleep_fn(min(2**attempt_number, 30))  # exponential backoff, capped at 30s

    with get_db_session() as db:
        notification = crud.get_notification(db, notification_id)
        # last_error was already persisted by record_attempt_failure above
        # (or, if max_attempts was somehow 0, notification.last_error is
        # just None -- mark_failed handles that fine either way).
        crud.mark_failed(db, notification, notification.last_error or "max attempts exhausted")
