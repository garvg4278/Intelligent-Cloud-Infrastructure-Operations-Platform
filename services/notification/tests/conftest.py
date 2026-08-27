import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database_module
from app.database import Base, get_db
from app.main import app
from app.sender import set_sender_registry
from app.tasks import celery_app

from .fakes import FakeSender


@pytest.fixture(autouse=True)
def celery_eager():
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery_app.conf.update(task_always_eager=False)


@pytest.fixture()
def webhook_sender():
    fake = FakeSender()
    set_sender_registry({"webhook": fake})
    yield fake
    set_sender_registry(None)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original = database_module.SessionLocal
    database_module.SessionLocal = TestingSessionLocal

    session = TestingSessionLocal()
    yield session
    session.close()

    database_module.SessionLocal = original
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session, webhook_sender):
    with TestClient(app) as test_client:
        yield test_client
