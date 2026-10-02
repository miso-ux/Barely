"""Test setup: a dedicated `barely_test` database, migrated once, reset and re-seeded per test.

DATABASE_URL must be set before any `app` module is imported, hence the import order below.
"""

import os
from urllib.parse import urlsplit, urlunsplit

_DEFAULT_URL = "postgresql+psycopg://barely:barely@db:5432/barely"
_PARTS = urlsplit(os.environ.get("DATABASE_URL", _DEFAULT_URL))
TEST_DB_NAME = "barely_test"
os.environ["DATABASE_URL"] = urlunsplit(_PARTS._replace(path=f"/{TEST_DB_NAME}"))
os.environ["SCHEDULER_ENABLED"] = "false"

import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import seed  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

DEMO_PASSWORD = seed.DEMO_PASSWORD


@pytest.fixture(scope="session", autouse=True)
def database():
    with psycopg.connect(f"postgresql://{_PARTS.netloc}/postgres", autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    command.upgrade(Config("alembic.ini"), "head")
    yield


@pytest.fixture(autouse=True)
def reset_database(database):
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE audit_log, settings, user_roles, role_permissions, "
                "users, roles, permissions, barrel_status_history, barrels, "
                "notifications, penalties, loans, exception_requests, orders "
                "RESTART IDENTITY CASCADE"
            )
        )
        conn.execute(text("ALTER SEQUENCE barrel_code_seq RESTART WITH 1"))
    seed.run(quiet=True)
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


def login(client: TestClient, username: str, password: str = DEMO_PASSWORD):
    return client.post("/login", data={"username": username, "password": password})


def login_admin(client: TestClient, new_password: str = "AdminNew123!") -> str:
    """The seeded admin must change the password first; do it and return the new password."""
    login(client, "admin")
    response = client.post(
        "/password",
        data={
            "current_password": DEMO_PASSWORD,
            "new_password": new_password,
            "new_password_confirm": new_password,
        },
    )
    assert response.status_code == 303, response.text
    return new_password


@pytest.fixture
def admin_client(client: TestClient) -> TestClient:
    login_admin(client)
    return client
