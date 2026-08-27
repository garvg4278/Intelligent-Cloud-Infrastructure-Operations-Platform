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
    """Autouse so every existing test gets a working fake by default --
    register/login now call the audit client as a side effect, and
    nothing about that should require every pre-existing test to know
    about it. Tests that specifically care about auditing behavior use
    the yielded fake directly.
    """
    fake = FakeAuditClient()
    set_audit_client(fake)
    yield fake
    set_audit_client(None)


@pytest.fixture()
def db_session():
    # StaticPool + check_same_thread=False so every connection request
    # against this in-memory SQLite DB reuses the same connection --
    # otherwise SQLAlchemy's default pooling opens a fresh (empty) in-memory
    # DB per connection and every query after the first fails with
    # "no such table".
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

    session = TestingSessionLocal()
    yield session
    session.close()

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    with TestClient(app) as test_client:
        yield test_client
