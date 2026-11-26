"""Integration tests for Task Assignment, Tags (Many-to-Many), and /tasks/my-tasks."""

from tests.conftest import authenticated_client as client
from tests.conftest import client as anonymous_client


def _create_user_and_login(username="dev_member", email="dev@domain.com", password="Password123"):
    reg = client.post(
        "/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
        },
    )
    assert reg.status_code == 201

    login = client.post(
        "/auth/login",
        json={
            "username": username,
            "password": password,
        },
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    user_id = reg.json()["id"]
    return token, user_id


# ══════════════════════════════════════════════════════════════════════════════
# TAGS CRUD TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestTags:
    def test_create_tag_success(self):
        resp = client.post("/tags", json={"name": "backend", "color": "#0ea5e9"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "backend"
        assert data["color"] == "#0ea5e9"
        assert "id" in data

    def test_create_tag_duplicate_name_rejected(self):
        client.post("/tags", json={"name": "duplicate_tag", "color": "#10b981"})
        resp = client.post("/tags", json={"name": "duplicate_tag", "color": "#f59e0b"})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_create_tag_invalid_hex_color(self):
        resp = client.post("/tags", json={"name": "invalid_color", "color": "not_a_color"})
        assert resp.status_code == 422

    def test_list_tags(self):
        client.post("/tags", json={"name": "frontend", "color": "#f43f5e"})
        client.post("/tags", json={"name": "devops", "color": "#8b5cf6"})

        resp = client.get("/tags")
        assert resp.status_code == 200
        tags = resp.json()
        names = [t["name"] for t in tags]
        assert "frontend" in names
        assert "devops" in names

    def test_delete_tag_success(self):
        tag = client.post("/tags", json={"name": "temporary", "color": "#333333"}).json()
        del_resp = client.delete(f"/tags/{tag['id']}")
        assert del_resp.status_code == 204

        # Verify gone
        list_resp = client.get("/tags")
        assert not any(t["id"] == tag["id"] for t in list_resp.json())

    def test_delete_tag_not_found(self):
        resp = client.delete("/tags/99999")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# TASK TAGS ASSOCIATION TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestTaskTagsAssociation:
    def test_create_task_with_initial_tags(self):
        t1 = client.post("/tags", json={"name": "bug", "color": "#ef4444"}).json()
        t2 = client.post("/tags", json={"name": "security", "color": "#8b5cf6"}).json()

        p = client.post("/projects", json={"name": "Secure Project"}).json()
        task_resp = client.post(
            f"/projects/{p['id']}/tasks",
            json={
                "title": "Fix SQL injection",
                "tag_ids": [t1["id"], t2["id"]],
            },
        )
        assert task_resp.status_code == 201
        data = task_resp.json()
        assert len(data["tags"]) == 2
        tag_names = [t["name"] for t in data["tags"]]
        assert "bug" in tag_names
        assert "security" in tag_names

    def test_add_and_remove_tag_from_task(self):
        tag = client.post("/tags", json={"name": "feature", "color": "#10b981"}).json()
        p = client.post("/projects", json={"name": "Feature Project"}).json()
        t = client.post(f"/projects/{p['id']}/tasks", json={"title": "Add OAuth"}).json()

        # Add tag
        add_resp = client.post(f"/tasks/{t['id']}/tags/{tag['id']}")
        assert add_resp.status_code == 200
        assert any(x["id"] == tag["id"] for x in add_resp.json()["tags"])

        # Remove tag
        rem_resp = client.delete(f"/tasks/{t['id']}/tags/{tag['id']}")
        assert rem_resp.status_code == 200
        assert not any(x["id"] == tag["id"] for x in rem_resp.json()["tags"])

    def test_filter_tasks_by_tag(self):
        t_urgent = client.post("/tags", json={"name": "critical", "color": "#dc2626"}).json()
        p = client.post("/projects", json={"name": "Tag Filter Project"}).json()

        # Task with tag
        client.post(
            f"/projects/{p['id']}/tasks",
            json={
                "title": "Server outage",
                "tag_ids": [t_urgent["id"]],
            },
        )
        # Task without tag
        client.post(f"/projects/{p['id']}/tasks", json={"title": "Update logo"})

        resp = client.get("/tasks?tag=critical")
        assert resp.status_code == 200
        tasks = resp.json()["items"]
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Server outage"


# ══════════════════════════════════════════════════════════════════════════════
# TASK ASSIGNMENT & /tasks/my-tasks TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestTaskAssignment:
    def test_create_task_with_assignee(self):
        _, user_id = _create_user_and_login("assignee_user", "assignee@domain.com")
        p = client.post("/projects", json={"name": "Assigned Project"}).json()

        task_resp = client.post(
            f"/projects/{p['id']}/tasks",
            json={
                "title": "Implement feature X",
                "assignee_id": user_id,
            },
        )
        assert task_resp.status_code == 201
        assert task_resp.json()["assignee_id"] == user_id

    def test_update_task_assignee(self):
        _, user1_id = _create_user_and_login("user_one", "u1@domain.com")
        _, user2_id = _create_user_and_login("user_two", "u2@domain.com")

        p = client.post("/projects", json={"name": "Reassignment Project"}).json()
        t = client.post(
            f"/projects/{p['id']}/tasks",
            json={
                "title": "Initial task",
                "assignee_id": user1_id,
            },
        ).json()

        # Reassign to user2
        update_resp = client.patch(f"/tasks/{t['id']}", json={"assignee_id": user2_id})
        assert update_resp.status_code == 200
        assert update_resp.json()["assignee_id"] == user2_id

    def test_list_my_tasks_authenticated(self):
        token, user_id = _create_user_and_login("my_tasks_user", "mytasks@domain.com")
        p = client.post("/projects", json={"name": "My Work Project"}).json()

        # Task 1 assigned to this user
        client.post(
            f"/projects/{p['id']}/tasks",
            json={
                "title": "My Task 1",
                "assignee_id": user_id,
                "status": "in_progress",
            },
        )
        # Task 2 assigned to someone else or unassigned
        client.post(f"/projects/{p['id']}/tasks", json={"title": "Someone Else Task"})

        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get("/tasks/my-tasks", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "My Task 1"
        assert data["items"][0]["assignee_id"] == user_id

    def test_list_my_tasks_unauthorized(self):
        resp = anonymous_client.get("/tasks/my-tasks")
        assert resp.status_code == 401

    def test_filter_tasks_by_assignee_id(self):
        _, user_id = _create_user_and_login("filter_assignee", "filter@domain.com")
        p = client.post("/projects", json={"name": "Assignee Filter Project"}).json()

        client.post(
            f"/projects/{p['id']}/tasks",
            json={
                "title": "Target Assigned Task",
                "assignee_id": user_id,
            },
        )
        client.post(f"/projects/{p['id']}/tasks", json={"title": "Unassigned Task"})

        resp = client.get(f"/tasks?assignee_id={user_id}")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["title"] == "Target Assigned Task"
