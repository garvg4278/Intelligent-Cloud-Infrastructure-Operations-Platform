import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.audit_client import set_audit_client
from app.database import Base, get_db
from app.main import app

from .fakes import FakeAuditClient


@pytest.fixture(autouse=True)
def audit_client():
    """Autouse -- creating an incident and transitioning its status now
    call the audit client as a side effect. Same reasoning as the
    equivalent fixture in auth/deployment/alert's conftest.py.
    """
    fake = FakeAuditClient()
    set_audit_client(fake)
    yield fake
    set_audit_client(None)


@pytest.fixture()
def client():
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
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
