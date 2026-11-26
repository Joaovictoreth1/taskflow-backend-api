import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from pydantic import ValidationError
from sqlalchemy import event, select

from app import crud, models, schemas
from app.config import Settings
from app.main import limiter
from app.security import create_access_token, credential_stamp, hash_password
from tests.conftest import (
    TestingSessionLocal,
    auth_headers,
    authenticated_client,
    client,
    test_engine,
)


def account(username: str, *, active: bool = True, password: str | None = None) -> models.User:
    with TestingSessionLocal.begin() as db:
        user = models.User(
            username=username,
            email=f"{username}@example.test",
            is_active=active,
            hashed_password=hash_password(password) if password else "not-a-login-password",
        )
        db.add(user)
        db.flush()
        return user


def workspace(owner: dict[str, str], assignee_id: int | None = None) -> tuple[int, int]:
    project = client.post("/projects", headers=owner, json={"name": "Workspace"})
    assert project.status_code == 201
    project_id = project.json()["id"]
    task = client.post(
        f"/projects/{project_id}/tasks",
        headers=owner,
        json={"title": "Task", "assignee_id": assignee_id},
    )
    assert task.status_code == 201
    return project_id, task.json()["id"]


@pytest.mark.parametrize("chunked", [False, True])
def test_oversized_body_is_rejected_before_validation_and_keeps_cors_headers(chunked):
    from app.config import settings

    limit = settings.max_request_body_bytes
    chunk = b"x" * (limit // 2 + 1)
    body = iter((chunk, chunk)) if chunked else chunk + chunk
    response = client.post(
        "/auth/login", content=body, headers={"Origin": "https://ui.example.test"}
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}
    assert response.headers["access-control-allow-origin"] == "https://ui.example.test"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "path", ["/projects", "/tasks", "/tags", "/analytics/overview", "/students"]
)
def test_private_endpoints_require_active_authentication(path):
    assert client.get(path).status_code == 401
    inactive = auth_headers(account("inactive", active=False))
    assert client.get(path, headers=inactive).status_code != 200


def test_unrelated_users_cannot_access_projects_tasks_or_derived_data():
    owner = auth_headers(account("owner"))
    outsider = auth_headers(account("outsider"))
    project, task = workspace(owner)
    for path in (
        f"/projects/{project}",
        f"/projects/{project}/tasks",
        f"/projects/{project}/stats",
        f"/projects/{project}/export/csv",
        f"/tasks/{task}",
        f"/tasks/{task}/comments",
    ):
        assert client.get(path, headers=outsider).status_code == 404
    assert client.get("/projects/paginated", headers=outsider).json()["total"] == 0
    assert client.get("/tasks", headers=outsider).json()["total"] == 0
    assert client.get("/analytics/overview", headers=outsider).json()["total_tasks"] == 0
    assert (
        client.patch(f"/tasks/{task}", headers=outsider, json={"status": "done"}).status_code == 404
    )
    assert client.delete(f"/projects/{project}", headers=outsider).status_code == 404
    assert client.get(f"/tasks/{task}", headers=owner).json()["status"] == "todo"


def test_assignment_grants_only_task_and_comment_access():
    owner = auth_headers(account("owner"))
    peer = account("peer")
    assigned = auth_headers(peer)
    project, task = workspace(owner, peer.id)
    _, other_task = workspace(owner, peer.id)
    assert client.get("/tasks/my-tasks", headers=assigned).json()["total"] == 2
    assert client.get(f"/projects/{project}", headers=assigned).status_code == 404
    assert client.get(f"/tasks/{task}", headers=assigned).status_code == 200
    assert (
        client.patch(f"/tasks/{task}", headers=assigned, json={"status": "done"}).status_code == 404
    )
    assert client.delete(f"/tasks/{task}", headers=assigned).status_code == 404

    def comment(headers):
        response = client.post(
            f"/tasks/{task}/comments", headers=headers, json={"content": "Review"}
        )
        assert response.status_code == 201
        return response.json()["id"]

    author_comment, owner_comment = comment(assigned), comment(owner)
    assert (
        client.delete(f"/tasks/{other_task}/comments/{owner_comment}", headers=owner).status_code
        == 404
    )
    assert (
        client.delete(f"/tasks/{task}/comments/{owner_comment}", headers=assigned).status_code
        == 404
    )
    assert (
        client.delete(f"/tasks/{task}/comments/{author_comment}", headers=assigned).status_code
        == 204
    )
    assert (
        client.delete(f"/tasks/{task}/comments/{owner_comment}", headers=owner).status_code == 204
    )
    assert (
        client.patch(f"/tasks/{task}", headers=owner, json={"assignee_id": None}).status_code == 200
    )
    assert client.get(f"/tasks/{task}", headers=assigned).status_code == 404


def test_directory_and_tag_boundaries():
    owner = auth_headers(account("owner"))
    outsider = auth_headers(account("outsider"))
    assert client.get("/students", headers=owner).status_code == 403
    assert (
        client.post(
            "/students", headers=owner, json={"name": "Someone", "email": "s@example.test"}
        ).status_code
        == 403
    )
    project, task = workspace(owner)
    theirs = client.post("/tags", headers=outsider, json={"name": "private"}).json()["id"]
    mine = client.post("/tags", headers=owner, json={"name": "private"}).json()["id"]
    assert mine != theirs
    assert [tag["id"] for tag in client.get("/tags", headers=owner).json()] == [mine]
    assert client.delete(f"/tags/{theirs}", headers=owner).status_code == 404
    assert client.post(f"/tasks/{task}/tags/{theirs}", headers=owner).status_code == 404
    assert (
        client.post(
            f"/projects/{project}/tasks",
            headers=owner,
            json={"title": "Wrong tag", "tag_ids": [theirs]},
        ).status_code
        == 404
    )
    for _ in range(2):
        assert [
            tag["id"]
            for tag in client.post(f"/tasks/{task}/tags/{mine}", headers=owner).json()["tags"]
        ] == [mine]
    for _ in range(2):
        assert client.delete(f"/tasks/{task}/tags/{mine}", headers=owner).json()["tags"] == []


def test_ownerless_projects_and_assignments_are_quarantined():
    peer = account("peer")
    with TestingSessionLocal.begin() as db:
        task = models.Task(
            project=models.Project(name="Unclaimed"), title="Old", assignee_id=peer.id
        )
        db.add(task)
        db.flush()
        project_id, task_id = task.project_id, task.id
    headers = auth_headers(peer)
    assert client.get(f"/projects/{project_id}", headers=headers).status_code == 404
    assert client.get(f"/tasks/{task_id}", headers=headers).status_code == 404
    assert client.get("/tasks/my-tasks", headers=headers).json()["total"] == 0


def test_invalid_filters_and_foreign_keys_are_client_errors():
    owner = auth_headers(account("owner"))
    project, task = workspace(owner)
    for path in (
        "/tasks?status=other",
        "/tasks?priority=other",
        "/tasks?assignee_id=987654321098765",
        "/tasks/987654321098765",
    ):
        assert client.get(path, headers=owner).status_code == 422
    assert client.patch(f"/tasks/{task}", headers=owner, json={"status": None}).status_code == 422
    assert (
        client.patch(f"/projects/{project}", headers=owner, json={"name": None}).status_code == 422
    )
    disabled = account("disabled", active=False)
    assert (
        client.patch(f"/tasks/{task}", headers=owner, json={"assignee_id": disabled.id}).status_code
        == 404
    )
    assert (
        client.post(f"/tasks/{task}/comments", headers=owner, json={"content": "  "}).status_code
        == 422
    )


def test_csv_neutralizes_formulas_and_preserves_ordinary_data():
    project_id = authenticated_client.post("/projects", json={"name": "Export"}).json()["id"]
    path = f"/projects/{project_id}"
    body = {
        "title": "=summary",
        "description": "\t@data, quoted\nsecond line",
        "due_date": "2026-11-19T04:30:00-03:00",
    }
    response = authenticated_client.post(f"{path}/tasks", json=body)
    assert response.json()["due_date"] == "2026-11-19T07:30:00Z"
    exported = authenticated_client.get(f"{path}/export/csv")
    row = next(csv.DictReader(exported.text.splitlines(keepends=True)))
    assert row["Title"] == "'=summary"
    assert row["Description"] == "'" + body["description"]


def test_form_auth_token_expiry_and_password_rotation():
    user = account("account", password="old-password")
    response = client.post(
        "/auth/token", data={"username": user.username, "password": "old-password"}
    )
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/auth/me", headers=headers).status_code == 200
    expired = create_access_token(
        {"sub": user.username, "user_id": user.id, "pwd": credential_stamp(user.hashed_password)},
        expires_delta=timedelta(seconds=-1),
    )
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    assert (
        client.post(
            "/auth/change-password",
            headers=headers,
            json={"old_password": "old-password", "new_password": "new-password"},
        ).status_code
        == 200
    )
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert (
        client.post(
            "/auth/login", json={"username": user.username, "password": "new-password"}
        ).status_code
        == 200
    )


def test_password_validation_does_not_echo_input():
    password = "ã" * 40
    invalid = client.post(
        "/auth/register",
        json={"username": "new_user", "email": "new@example.test", "password": password},
    )
    assert invalid.status_code == 422
    assert "72 UTF-8 bytes" in invalid.text
    assert password not in invalid.text
    assert "input" not in invalid.json()["detail"][0]


def test_headers_origin_and_readiness():
    response = client.get("/health", headers={"Origin": "https://ui.example.test"})
    assert response.headers["Access-Control-Allow-Origin"] == "https://ui.example.test"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"
    assert (
        "Access-Control-Allow-Origin"
        not in client.get("/health", headers={"Origin": "https://elsewhere.test"}).headers
    )
    assert client.get("/ready").status_code == 503


def test_configuration_rejects_unusable_production_defaults(monkeypatch):
    for env_var in (
        "APP_ENV",
        "SECRET_KEY",
        "DATABASE_URL",
        "RATE_LIMIT_STORAGE_URI",
        "CORS_ORIGINS",
    ):
        monkeypatch.delenv(env_var)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings(_env_file=None).signing_key()
    with pytest.raises(ValidationError, match="requires PostgreSQL"):
        Settings(_env_file=None, app_env="production")
    with pytest.raises(ValidationError, match="requires shared Redis"):
        Settings(_env_file=None, app_env="production", database_url="postgresql://db/tasks")
    with pytest.raises(ValidationError, match="explicit"):
        Settings(_env_file=None, cors_origins=["*"])
    with pytest.raises(ValidationError, match="Invalid database URL"):
        Settings(_env_file=None, database_url="invalid")
    assert (
        Settings(_env_file=None, database_url="postgresql://db/tasks").sqlalchemy_url.drivername
        == "postgresql+psycopg"
    )


def test_auth_rate_limit():
    limiter.reset()
    limiter.enabled = True
    try:
        for _ in range(10):
            assert (
                client.post(
                    "/auth/login", json={"username": "unknown", "password": "irrelevant"}
                ).status_code
                == 401
            )
        assert (
            client.post(
                "/auth/login", json={"username": "unknown", "password": "irrelevant"}
            ).status_code
            == 429
        )
    finally:
        limiter.enabled = False
        limiter.reset()


def test_database_conflict_rolls_back_cleanly():
    user = account("tag_owner")
    with TestingSessionLocal() as db:
        crud.create_tag(db, schemas.TagCreate(name="unique"), owner_id=user.id)
        with pytest.raises(crud.WriteConflict):
            crud.create_tag(db, schemas.TagCreate(name="unique"), owner_id=user.id)
        assert crud.get_tag_by_name(db, "unique", owner_id=user.id) is not None


@pytest.mark.skipif(
    test_engine.dialect.name != "postgresql", reason="requires independent PostgreSQL transactions"
)
def test_concurrent_tag_attachment_is_idempotent():
    owner = account("owner")
    _, task_id = workspace(auth_headers(owner))
    with TestingSessionLocal() as db:
        tag_id = crud.create_tag(db, schemas.TagCreate(name="tag"), owner_id=owner.id).id
    barrier = Barrier(2)

    def attach():
        with TestingSessionLocal() as db:
            task = crud.get_task(db, task_id, actor_id=owner.id, owner_only=True)
            assert task is not None
            barrier.wait(timeout=10)
            crud.set_task_tag(db, task, tag_id, owner_id=owner.id, attached=True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.submit(attach), executor.submit(attach)
        first.result(timeout=15)
        second.result(timeout=15)
    with TestingSessionLocal() as db:
        assert db.execute(select(models.task_tags)).all() == [(task_id, tag_id)]


def test_query_budget_for_task_page_and_overview():
    owner = account("owner")
    with TestingSessionLocal.begin() as db:
        project = models.Project(owner_id=owner.id, name="Query budget")
        tag = models.Tag(owner_id=owner.id, name="label")
        db.add_all([project, tag])
        db.add_all([models.Task(project=project, title=f"Task {i}", tags=[tag]) for i in range(25)])

    statements = []

    def after_execute(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(test_engine, "after_cursor_execute", after_execute)
    try:
        headers = auth_headers(owner)
        response = client.get("/tasks?size=25", headers=headers)
        assert response.json()["total"] == 25
        assert all(task["tags"] for task in response.json()["items"])
        assert len(statements) == 4  # Authentication, count, page, batched tags
        statements.clear()
        assert client.get("/analytics/overview", headers=headers).json()["total_tasks"] == 25
        assert len(statements) == 2  # Authentication and SQL aggregates
    finally:
        event.remove(test_engine, "after_cursor_execute", after_execute)
