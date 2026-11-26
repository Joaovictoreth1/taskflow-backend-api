import os
from pathlib import Path
import subprocess
import sys

import jwt
import pytest

from app.config import jwt_settings
from app.security import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY, decode_access_token
from tests.conftest import client


def register(username: str) -> dict[str, str]:
    data = {
        "username": username,
        "email": f"{username}@example.com",
        "password": "test-only-password",
    }
    assert client.post("/auth/register", json=data).status_code == 201
    return data


def auth(username: str) -> dict[str, str]:
    response = client.post("/auth/login", json=register(username))
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_missing_signing_key_fails_explicitly(monkeypatch):
    monkeypatch.delenv("SECRET_KEY")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        jwt_settings()


def test_token_without_expiry_is_rejected():
    token = jwt.encode({"sub": "test_owner"}, SECRET_KEY, algorithm=ALGORITHM)
    assert decode_access_token(token) is None


def test_app_import_and_unapproved_seed_do_not_create_database(tmp_path: Path):
    database = tmp_path / "not-created.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database}", "TASKFLOW_SEED_DEMO": ""}
    subprocess.run([sys.executable, "-c", "import app.main"], check=True, env=env)
    seed = subprocess.run(
        [sys.executable, "seed.py"], capture_output=True, text=True, env=env
    )
    assert seed.returncode != 0
    assert "TASKFLOW_SEED_DEMO=1" in seed.stderr
    assert not database.exists()


def test_form_login_advertises_configured_token_expiration():
    user = register("form_user")
    response = client.post(
        "/auth/login", data={"username": user["username"], "password": user["password"]}
    )
    assert response.status_code == 200
    assert response.json()["expires_in_minutes"] == ACCESS_TOKEN_EXPIRE_MINUTES


def test_password_limit_counts_utf8_bytes():
    response = client.post(
        "/auth/register",
        json={"username": "long_pw", "email": "long@example.com", "password": "é" * 37},
    )
    assert response.status_code == 422


def test_owned_projects_and_tasks_reject_unauthorized_changes():
    owner = auth("test_owner")
    outsider = auth("test_outsider")
    project = client.post("/projects", json={"name": "Owned"}, headers=owner)
    assert project.status_code == 201
    path = f"/projects/{project.json()['id']}"

    assert client.patch(path, json={"name": "Changed"}).status_code == 401
    assert client.delete(path, headers=outsider).status_code == 403
    assert client.post(f"{path}/tasks", json={"title": "Task"}, headers=outsider).status_code == 403
    tag = client.post("/tags", json={"name": "owned-tag"}).json()["id"]
    task = client.post(f"{path}/tasks", json={"title": "Task", "tag_ids": [tag]}, headers=owner)
    assert task.status_code == 201
    task_path = f"/tasks/{task.json()['id']}"
    assert client.patch(task_path, json={"title": "Changed"}, headers=outsider).status_code == 403
    assert client.patch(task_path, json={"title": "Changed"}, headers=owner).status_code == 200
    assert client.delete(f"/tags/{tag}").status_code == 409


def test_task_validation_and_comment_parent():
    response = client.post("/projects", json={"name": "Public demo"})
    tasks = f"/projects/{response.json()['id']}/tasks"
    assert client.post(tasks, json={"title": "Task", "assignee_id": 999}).status_code == 422
    first = client.post(tasks, json={"title": "First"}).json()["id"]
    second = client.post(tasks, json={"title": "Second"}).json()["id"]
    path = f"/tasks/{first}/comments"
    assert client.patch(f"/tasks/{first}", json={"title": None}).status_code == 422
    assert client.post(path, json={"content": "   "}).status_code == 422
    comment = client.post(path, json={"content": "Valid comment"}).json()["id"]
    assert client.delete(f"/tasks/{second}/comments/{comment}").status_code == 404
    assert client.get(path).json()[0]["id"] == comment
