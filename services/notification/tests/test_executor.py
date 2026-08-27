import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database_module
from app import crud, schemas
from app.database import Base
from app.executor import deliver_with_retries
from app.models import NotificationStatus

from .fakes import FakeSender, no_sleep


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    original = database_module.SessionLocal
    database_module.SessionLocal = TestingSessionLocal

    session = TestingSessionLocal()
    yield session
    session.close()
    database_module.SessionLocal = original
    Base.metadata.drop_all(bind=engine)


def _create(db_session, **overrides) -> str:
    payload = {
        "channel": "webhook", "target": "https://hooks.example.com/x",
        "subject": "Alert", "body": "something happened", "max_attempts": 3,
    }
    payload.update(overrides)
    notification = crud.create_notification(db_session, schemas.NotificationCreate(**payload))
    return notification.id


def test_delivers_successfully_on_first_attempt(db_session):
    sender = FakeSender(fail_times=0)
    notification_id = _create(db_session)

    deliver_with_retries(notification_id, {"webhook": sender}, sleep_fn=no_sleep)

    updated = crud.get_notification(db_session, notification_id)
    assert updated.status == NotificationStatus.sent
    assert updated.attempts == 0  # never recorded a FAILURE -- it just worked
    assert len(sender.calls) == 1


def test_retries_after_transient_failure_then_succeeds(db_session):
    sender = FakeSender(fail_times=2)  # fails twice, succeeds on the 3rd try
    notification_id = _create(db_session, max_attempts=3)

    deliver_with_retries(notification_id, {"webhook": sender}, sleep_fn=no_sleep)

    updated = crud.get_notification(db_session, notification_id)
    assert updated.status == NotificationStatus.sent
    assert updated.attempts == 2  # 2 recorded failures before the successful 3rd call
    assert len(sender.calls) == 3


def test_marks_failed_after_exhausting_max_attempts(db_session):
    sender = FakeSender(fail_times=10)  # never succeeds
    notification_id = _create(db_session, max_attempts=3)

    deliver_with_retries(notification_id, {"webhook": sender}, sleep_fn=no_sleep)

    updated = crud.get_notification(db_session, notification_id)
    assert updated.status == NotificationStatus.failed
    assert updated.attempts == 3
    assert "simulated failure #3" in updated.last_error
    assert len(sender.calls) == 3  # never tried a 4th time


def test_sleep_is_called_between_attempts_not_after_the_last_one(db_session):
    sleep_calls = []
    sender = FakeSender(fail_times=10)
    notification_id = _create(db_session, max_attempts=3)

    deliver_with_retries(notification_id, {"webhook": sender}, sleep_fn=sleep_calls.append)

    assert len(sleep_calls) == 2  # slept after attempt 1 and 2, not after the final attempt 3


def test_unknown_channel_marks_failed_without_touching_any_sender(db_session):
    notification_id = _create(db_session, channel="email")  # no sender registered for "email" here

    deliver_with_retries(notification_id, {"webhook": FakeSender()}, sleep_fn=no_sleep)

    updated = crud.get_notification(db_session, notification_id)
    assert updated.status == NotificationStatus.failed
    assert "no sender registered" in updated.last_error


def test_already_sent_notification_is_not_redelivered(db_session):
    sender = FakeSender(fail_times=0)
    notification_id = _create(db_session)
    deliver_with_retries(notification_id, {"webhook": sender}, sleep_fn=no_sleep)
    assert len(sender.calls) == 1

    # Calling it again (e.g. a duplicate task execution) must not re-send
    deliver_with_retries(notification_id, {"webhook": sender}, sleep_fn=no_sleep)
    assert len(sender.calls) == 1
