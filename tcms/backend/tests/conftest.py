import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from auth import hash_password
from database import Base, get_db
from main import app
from models import Project, TCIDSequence, Template, User

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        # single connection for the whole session so in-memory DB persists
        poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture(scope="function")
def db(engine):
    """Each test gets a transaction that is always rolled back."""
    connection = engine.connect()
    transaction = connection.begin()
    TestingSession = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = TestingSession()
    # For SQLite nested transaction support
    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, trans):
        if trans.nested and not trans._parent.nested:
            session.expire_all()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        # Disable rate limiting AFTER startup (startup resets limiter.enabled)
        from main import limiter as _main_limiter
        from routers.auth import limiter as _auth_limiter
        _main_limiter.enabled = False
        _auth_limiter.enabled = False
        yield c
    _main_limiter.enabled = True
    _auth_limiter.enabled = True
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db):
    user = User(email="admin@test.com", password_hash=hash_password("password123"),
                full_name="Admin User", role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def qa_user(db):
    user = User(email="qa@test.com", password_hash=hash_password("password123"),
                full_name="QA Lead", role="qa_lead")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_token(client, admin_user):
    resp = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "password123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def qa_token(client, qa_user):
    resp = client.post("/api/auth/login", json={"email": "qa@test.com", "password": "password123"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def project(client, db, admin_user, admin_token):
    resp = client.post("/api/projects",
        json={"name": "Test Project", "client_name": "Acme Corp"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def test_case(client, admin_token, project):
    resp = client.post(f"/api/projects/{project['id']}/testcases",
        json={"title": "Login happy path",
              "steps": "1. Go to /login\n2. Enter valid credentials\n3. Click Sign In",
              "expected_result": "Redirected to dashboard", "priority": "P1"},
        headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def react_template(db):
    t = Template(name="React CRUD App", type="react-crud",
                 cases=[{"title": "Login test", "steps": "1. Go to login", "expected_result": "Logged in", "priority": "P1"}] * 5)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t
