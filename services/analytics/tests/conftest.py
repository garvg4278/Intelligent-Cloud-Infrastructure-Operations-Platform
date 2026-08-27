import pytest
from fastapi.testclient import TestClient

from app.cache import set_cache_client
from app.main import app
from app.service_clients import set_alert_client, set_deployment_client, set_incident_client

from .fakes import FakeAlertClient, FakeCacheClient, FakeDeploymentClient, FakeIncidentClient


@pytest.fixture()
def deployment_client():
    fake = FakeDeploymentClient()
    set_deployment_client(fake)
    yield fake
    set_deployment_client(None)


@pytest.fixture()
def incident_client():
    fake = FakeIncidentClient()
    set_incident_client(fake)
    yield fake
    set_incident_client(None)


@pytest.fixture()
def alert_client():
    fake = FakeAlertClient()
    set_alert_client(fake)
    yield fake
    set_alert_client(None)


@pytest.fixture()
def cache_client():
    fake = FakeCacheClient()
    set_cache_client(fake)
    yield fake
    set_cache_client(None)


@pytest.fixture()
def client(deployment_client, incident_client, alert_client, cache_client):
    with TestClient(app) as test_client:
        yield test_client
