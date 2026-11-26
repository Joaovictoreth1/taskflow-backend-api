"""Shared fixtures for API tests."""

import os
import secrets
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

os.environ["APP_ENV"] = "test"
os.environ["SECRET_KEY"] = secrets.token_hex(32)
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["RATE_LIMIT_STORAGE_URI"] = "memory://"
os.environ["CORS_ORIGINS"] = '["https://ui.example.test"]'

from app.database import Base, build_engine, get_db
from app.main import app
from app.models import User
from app.security import create_access_token, credential_stamp

postgres_url = os.getenv("TEST_POSTGRES_URL")
test_schema = f"test_{uuid4().hex}"
test_url = (
    make_url(postgres_url).update_query_dict({"options": f"-csearch_path={test_schema}"})
    if postgres_url
    else "sqlite://"
)
test_engine = build_engine(test_url, shared_memory=True)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


def override_get_db() -> Iterator[Session]:
    with TestingSessionLocal() as db:
        yield db


app.state.limiter.enabled = False
app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)
authenticated_client = TestClient(app)


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        {"sub": user.username, "user_id": user.id, "pwd": credential_stamp(user.hashed_password)}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def isolated_postgres_schema() -> Iterator[None]:
    if not postgres_url:
        yield
        return
    admin_engine = build_engine(postgres_url)
    try:
        with admin_engine.begin() as db:
            db.execute(text(f'CREATE SCHEMA "{test_schema}"'))
        try:
            yield
        finally:
            test_engine.dispose()
            with admin_engine.begin() as db:
                db.execute(text(f'DROP SCHEMA "{test_schema}" CASCADE'))
    finally:
        admin_engine.dispose()


@pytest.fixture(autouse=True)
def setup_database(isolated_postgres_schema: None) -> Iterator[None]:
    Base.metadata.create_all(bind=test_engine)
    with TestingSessionLocal.begin() as db:
        admin = User(
            username="directory_admin",
            email="admin@example.test",
            hashed_password="not-a-login-password",
            is_superuser=True,
        )
        db.add(admin)
        db.flush()
        authenticated_client.headers.update(auth_headers(admin))
    yield
    authenticated_client.headers.pop("Authorization", None)
    Base.metadata.drop_all(bind=test_engine)
