import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.db.base import Base
from app.db.session import get_db
from app.db.init_db import init_db
from app.core.security import create_access_token
from app.models.user import User

# In-memory SQLite with StaticPool so all connections share the same in-memory DB
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    init_db(session)
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def doctor_token(db):
    user = db.query(User).filter(User.role == "doctor").first()
    return create_access_token(subject=user.id, role=user.role)


@pytest.fixture
def staff_token(db):
    user = db.query(User).filter(User.role == "hospital_staff").first()
    return create_access_token(subject=user.id, role=user.role)


@pytest.fixture
def donor_token(db):
    user = db.query(User).filter(User.role == "donor").first()
    return create_access_token(subject=user.id, role=user.role)


@pytest.fixture
def patient_token(db):
    user = db.query(User).filter(User.role == "patient").first()
    return create_access_token(subject=user.id, role=user.role)


@pytest.fixture
def ambulance_token(db):
    user = db.query(User).filter(User.role == "ambulance_operator").first()
    return create_access_token(subject=user.id, role=user.role)


@pytest.fixture
def coordinator_token(db):
    user = db.query(User).filter(User.role == "transplant_coordinator").first()
    return create_access_token(subject=user.id, role=user.role)


@pytest.fixture
def admin_token(db):
    user = db.query(User).filter(User.role == "admin").first()
    return create_access_token(subject=user.id, role=user.role)
