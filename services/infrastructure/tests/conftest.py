import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database_module
from app.ansible_orchestrator import set_ansible_orchestrator
from app.audit_client import set_audit_client
from app.database import Base, get_db
from app.main import app
from app.tasks import celery_app
from app.terraform_orchestrator import set_terraform_orchestrator

from .fakes import FakeAnsibleOrchestrator, FakeAuditClient, FakeTerraformOrchestrator


@pytest.fixture(autouse=True)
def celery_eager():
    # Run tasks synchronously, in-process, instead of publishing to a real
    # RabbitMQ broker. This is Celery's own supported testing mode, not a
    # workaround -- see https://docs.celeryq.dev/en/stable/userguide/testing.html
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False)


@pytest.fixture(autouse=True)
def audit_client():
    """Autouse -- provisioning and destroy now call the audit client as a
    side effect. Without this, tests still pass (the real HttpAuditClient's
    failure is caught and logged, see audit_client.py), but this keeps test
    runs hermetic and fast instead of quietly depending on a failed
    localhost connection, and lets tests assert on audit behavior directly.
    """
    fake = FakeAuditClient()
    set_audit_client(fake)
    yield fake
    set_audit_client(None)


@pytest.fixture()
def terraform():
    fake = FakeTerraformOrchestrator()
    set_terraform_orchestrator(fake)
    yield fake
    set_terraform_orchestrator(None)


@pytest.fixture()
def ansible():
    fake = FakeAnsibleOrchestrator()
    set_ansible_orchestrator(fake)
    yield fake
    set_ansible_orchestrator(None)


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

    # The Celery tasks don't go through FastAPI's DI -- they open their own
    # session via get_db_session(), which reads SessionLocal from this
    # module at call time. Point it at the same test engine so both the API
    # and the (eagerly-run) tasks see the same in-memory database.
    original_session_local = database_module.SessionLocal
    database_module.SessionLocal = TestingSessionLocal

    session = TestingSessionLocal()
    yield session
    session.close()

    database_module.SessionLocal = original_session_local
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session, terraform, ansible):
    with TestClient(app) as test_client:
        yield test_client
