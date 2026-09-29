import os
import tempfile

import pytest

# Configure environment BEFORE any app import.
_tmpdir = tempfile.mkdtemp(prefix="pappu_test_")
# SQLite by default (fast, no service needed). Setting DATABASE_URL runs the same
# suite against a real Postgres, which is what production uses — worth doing
# before a release, since SQLite silently tolerates things Postgres rejects
# (stricter typing, no implicit cross-type comparison, real transaction
# isolation). Example:
#   DATABASE_URL=postgresql+psycopg://crm:crm@127.0.0.1:5432/pappu_crm pytest
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmpdir}/test.db")
# Keep uploaded files out of the real storage dir so test runs never pollute
# (or accidentally commit into) backend/storage/uploads/.
os.environ["STORAGE_DIR"] = f"{_tmpdir}/uploads"
# Force console email so the suite never makes real SMTP calls, even when the
# developer's .env has EMAIL_PROVIDER=smtp.
os.environ["EMAIL_PROVIDER"] = "console"
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-0123456789")
# Don't spin up the real background scheduler for every TestClient in the suite.
os.environ["REMINDER_SCHEDULER_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.core import ratelimit  # noqa: E402
from app.db.base import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

STRONG_PASSWORD = "Str0ng!Passw0rd"


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ratelimit._hits.clear()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def register(client, email="admin@stail.com", name="Admin User", password=STRONG_PASSWORD):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": name},
    )


def login(client, email="admin@stail.com", password=STRONG_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def auth_headers(client, email="admin@stail.com", password=STRONG_PASSWORD):
    resp = login(client, email, password)
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.fixture
def admin(client):
    """First registered user bootstraps as super_admin."""
    resp = register(client)
    assert resp.status_code == 201, resp.text
    return auth_headers(client)


def create_user_as_admin(client, admin_headers, email, role, name="Test User"):
    resp = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={"email": email, "password": STRONG_PASSWORD, "full_name": name, "role": role},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]
