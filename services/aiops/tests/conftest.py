import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.llm_client import set_llm_client
from app.main import app
from app.service_clients import (
    set_alert_client,
    set_deployment_client,
    set_incident_client,
    set_metrics_client,
)

from .fakes import FakeAlertClient, FakeDeploymentClient, FakeIncidentClient, FakeMetricsClient


@pytest.fixture()
def llm_client():
    """Tests that need a specific scripted LLM behavior construct their
    own FakeLLMClient and call set_llm_client directly -- this fixture
    just guarantees teardown happens even if they forget."""
    yield
    set_llm_client(None)


@pytest.fixture()
def deployment_client():
    fake = FakeDeploymentClient()
    set_deployment_client(fake)
    yield fake
    set_deployment_client(None)


@pytest.fixture()
def alert_client():
    fake = FakeAlertClient()
    set_alert_client(fake)
    yield fake
    set_alert_client(None)


@pytest.fixture()
def incident_client():
    fake = FakeIncidentClient()
    set_incident_client(fake)
    yield fake
    set_incident_client(None)


@pytest.fixture()
def metrics_client():
    fake = FakeMetricsClient()
    set_metrics_client(fake)
    yield fake
    set_metrics_client(None)


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
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session, llm_client, deployment_client, alert_client, incident_client, metrics_client):
    with TestClient(app) as test_client:
        yield test_client
