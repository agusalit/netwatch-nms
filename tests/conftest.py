import os

# Set before any `app.*` import so config.py never reads real secrets —
# load_dotenv() in config.py won't override vars already in the environment.
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import require_login
from app.models.database import Base, get_db
from app.main import app

# In-memory SQLite, kept alive for the whole test session via StaticPool
# (default in-memory SQLite is per-connection and would otherwise vanish
# between requests). Completely separate from the real data/netwatch.db —
# tests never touch your actual device data.
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
# Route tests exercise route logic, not the login flow itself — that's
# covered separately in test_auth.py. Bypassing auth here keeps every
# existing route test working without needing a real login per test.
app.dependency_overrides[require_login] = lambda: "test-user"


@pytest.fixture(scope="session", autouse=True)
def _setup_test_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    # Deliberately NOT using `with TestClient(app) as client` — that would
    # trigger the real lifespan (init_db() against the real DATABASE_URL,
    # the APScheduler background poller, an immediate ICMP/SNMP sweep).
    # None of that is needed or wanted for route-level tests; the dependency
    # override above already gives every route our isolated test DB.
    return TestClient(app)


@pytest.fixture()
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def session_factory():
    """The test database's session factory, for code that opens its own
    sessions (e.g. the polling sweep) instead of going through get_db."""
    return TestingSessionLocal
