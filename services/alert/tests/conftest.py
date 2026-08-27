import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database_module
from app.audit_client import set_audit_client
from app.database import Base, get_db
from app.incident_client import set_incident_client
from app.main import app
from app.metrics_source import set_metrics_source
from app.notifier import set_notifier
from app.tasks import celery_app

from .fakes import FakeAuditClient, FakeIncidentClient, FakeMetricsSource, FakeNotifier


@pytest.fixture(autouse=True)
def celery_eager():
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False)


@pytest.fixture(autouse=True)
def audit_client():
    """Autouse -- acknowledging an alert now calls the audit client as a
    side effect. Same reasoning as the equivalent fixture in the auth and
    deployment services' conftest.py.
    """
    fake = FakeAuditClient()
    set_audit_client(fake)
    yield fake
    set_audit_client(None)


@pytest.fixture()
def metrics_source():
    fake = FakeMetricsSource()
    set_metrics_source(fake)
    yield fake
    set_metrics_source(None)


@pytest.fixture()
def notifier():
    fake = FakeNotifier()
    set_notifier(fake)
    yield fake
    set_notifier(None)


@pytest.fixture()
def incident_client():
    fake = FakeIncidentClient()
    set_incident_client(fake)
    yield fake
    set_incident_client(None)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    original_session_local = database_module.SessionLocal
    database_module.SessionLocal = TestingSessionLocal

    session = TestingSessionLocal()
    yield session
    session.close()

    database_module.SessionLocal = original_session_local
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session, metrics_source, notifier, incident_client):
    with TestClient(app) as test_client:
        yield test_client
