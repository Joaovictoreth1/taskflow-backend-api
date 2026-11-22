"""Integration tests for Analytics, Task Comments, User Management, and CSV Export."""

from datetime import datetime, timezone, timedelta
from tests.conftest import client


def _create_user_and_login(username="ana_dev", email="ana@example.com", password="SecurePassword123"):
    reg_resp = client.post("/auth/register", json={
        "username": username,
        "email": email,
        "password": password,
    })
    assert reg_resp.status_code == 201

    login_resp = client.post("/auth/login", json={
        "username": username,
        "password": password,
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return token, reg_resp.json()


# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS & STATS TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestAnalytics:

    def test_analytics_overview_empty(self):
        resp = client.get("/analytics/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_projects"] == 0
        assert data["total_tasks"] == 0
        assert data["completed_tasks"] == 0
        assert data["completion_rate_percent"] == 0.0

    def test_analytics_overview_with_tasks_and_kpis(self):
        # Create a project
        p_resp = client.post("/projects", json={"name": "Analytics Project"})
        pid = p_resp.json()["id"]

        now = datetime.now(timezone.utc)
        past_date = (now - timedelta(days=2)).isoformat()
        future_date = (now + timedelta(days=5)).isoformat()

        # Task 1: done
        client.post(f"/projects/{pid}/tasks", json={
            "title": "Task 1",
            "status": "done",
            "priority": "high",
        })
        # Task 2: in_progress overdue
        client.post(f"/projects/{pid}/tasks", json={
            "title": "Task 2 Overdue",
            "status": "in_progress",
            "priority": "urgent",
            "due_date": past_date,
        })
        # Task 3: todo on track
        client.post(f"/projects/{pid}/tasks", json={
            "title": "Task 3 On Track",
            "status": "todo",
            "priority": "medium",
            "due_date": future_date,
        })

        resp = client.get("/analytics/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_projects"] >= 1
        assert data["total_tasks"] == 3
        assert data["completed_tasks"] == 1
        assert data["in_progress_tasks"] == 1
        assert data["todo_tasks"] == 1
        assert data["overdue_tasks"] == 1
        assert data["completion_rate_percent"] == 33.33
        assert data["tasks_by_priority"]["urgent"] == 1
        assert data["tasks_by_priority"]["high"] == 1
        assert data["tasks_by_priority"]["medium"] == 1

    def test_project_stats_success(self):
        p_resp = client.post("/projects", json={"name": "Project Metrics"})
        pid = p_resp.json()["id"]

        client.post(f"/projects/{pid}/tasks", json={"title": "Done A", "status": "done"})
        client.post(f"/projects/{pid}/tasks", json={"title": "Done B", "status": "done"})
        client.post(f"/projects/{pid}/tasks", json={"title": "Pending", "status": "todo"})

        resp = client.get(f"/projects/{pid}/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["project_id"] == pid
        assert stats["project_name"] == "Project Metrics"
        assert stats["total_tasks"] == 3
        assert stats["completed_tasks"] == 2
        assert stats["todo_tasks"] == 1
        assert stats["completion_rate_percent"] == 66.67

    def test_project_stats_not_found(self):
        resp = client.get("/projects/99999/stats")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# USER MANAGEMENT & PASSWORD CHANGE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestUserManagement:

    def test_update_me_email_success(self):
        token, _ = _create_user_and_login("carlos_ops", "carlos@ops.com")
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.patch(
            "/auth/me",
            json={"email": "carlos_new@ops.com"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "carlos_new@ops.com"

    def test_update_me_duplicate_email_fails(self):
        _create_user_and_login("existing_user", "taken@domain.com")
        token2, _ = _create_user_and_login("second_user", "second@domain.com")

        resp = client.patch(
            "/auth/me",
            json={"email": "taken@domain.com"},
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert resp.status_code == 400
        assert "already in use" in resp.json()["detail"].lower()

    def test_change_password_success(self):
        token, _ = _create_user_and_login("pwd_user", "pwd@domain.com", "OldPassword123")
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post(
            "/auth/change-password",
            json={
                "old_password": "OldPassword123",
                "new_password": "NewSecretPassword456",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Verify old password no longer works
        failed_login = client.post("/auth/login", json={
            "username": "pwd_user",
            "password": "OldPassword123",
        })
        assert failed_login.status_code == 401

        # Verify new password works
        success_login = client.post("/auth/login", json={
            "username": "pwd_user",
            "password": "NewSecretPassword456",
        })
        assert success_login.status_code == 200

    def test_change_password_wrong_old_fails(self):
        token, _ = _create_user_and_login("wrong_old", "wrong@domain.com", "InitialPass123")
        resp = client.post(
            "/auth/change-password",
            json={
                "old_password": "IncorrectPassword",
                "new_password": "BrandNewPass999",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert "incorrect" in resp.json()["detail"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# TASK COMMENTS TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestTaskComments:

    def test_create_comment_anonymous(self):
        p = client.post("/projects", json={"name": "Comments Project"}).json()
        t = client.post(f"/projects/{p['id']}/tasks", json={"title": "Discuss Me"}).json()

        resp = client.post(
            f"/tasks/{t['id']}/comments",
            json={"content": "Here is an anonymous observation."},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["task_id"] == t["id"]
        assert data["content"] == "Here is an anonymous observation."
        assert data["author_name"] == "Anonymous"
        assert "id" in data

    def test_create_comment_authenticated(self):
        token, user = _create_user_and_login("commenter", "commenter@domain.com")
        p = client.post("/projects", json={"name": "Auth Comments Project"}).json()
        t = client.post(f"/projects/{p['id']}/tasks", json={"title": "Auth Task"}).json()

        resp = client.post(
            f"/tasks/{t['id']}/comments",
            json={"content": "Fixing this in branch feat/comments."},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["author_name"] == "commenter"
        assert data["user_id"] == user["id"]

    def test_create_comment_task_not_found(self):
        resp = client.post("/tasks/99999/comments", json={"content": "Test"})
        assert resp.status_code == 404

    def test_list_comments_chronological(self):
        p = client.post("/projects", json={"name": "Timeline Project"}).json()
        t = client.post(f"/projects/{p['id']}/tasks", json={"title": "Timeline Task"}).json()

        client.post(f"/tasks/{t['id']}/comments", json={"content": "First comment"})
        client.post(f"/tasks/{t['id']}/comments", json={"content": "Second comment"})

        resp = client.get(f"/tasks/{t['id']}/comments")
        assert resp.status_code == 200
        comments = resp.json()
        assert len(comments) == 2
        assert comments[0]["content"] == "First comment"
        assert comments[1]["content"] == "Second comment"

    def test_delete_comment_success(self):
        p = client.post("/projects", json={"name": "Del Comm Project"}).json()
        t = client.post(f"/projects/{p['id']}/tasks", json={"title": "Del Comm Task"}).json()

        c = client.post(f"/tasks/{t['id']}/comments", json={"content": "To be removed"}).json()

        del_resp = client.delete(f"/tasks/{t['id']}/comments/{c['id']}")
        assert del_resp.status_code == 204

        # List should now be empty
        list_resp = client.get(f"/tasks/{t['id']}/comments")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 0

    def test_delete_comment_not_found(self):
        resp = client.delete("/tasks/1/comments/99999")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# PROJECT CSV EXPORT TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestProjectExport:

    def test_export_project_tasks_csv_success(self):
        p = client.post("/projects", json={"name": "Export Project", "description": "Desc"}).json()
        pid = p["id"]

        client.post(f"/projects/{pid}/tasks", json={
            "title": "Backend Architecture",
            "status": "done",
            "priority": "urgent",
            "description": "Setup FastAPI with PostgreSQL",
        })
        client.post(f"/projects/{pid}/tasks", json={
            "title": "Frontend React",
            "status": "in_progress",
            "priority": "high",
        })

        resp = client.get(f"/projects/{pid}/export/csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert f"filename=project_{pid}_tasks.csv" in resp.headers["content-disposition"]

        text = resp.text
        lines = text.strip().split("\r\n") if "\r\n" in text else text.strip().split("\n")
        assert len(lines) == 3  # Header + 2 tasks
        assert "ID,Title,Status,Priority,Due Date,Created At,Description" in lines[0]
        assert "Backend Architecture" in lines[1] or "Backend Architecture" in lines[2]
        assert "Frontend React" in lines[1] or "Frontend React" in lines[2]

    def test_export_project_not_found(self):
        resp = client.get("/projects/99999/export/csv")
        assert resp.status_code == 404
