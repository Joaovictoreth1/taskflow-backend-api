"""Comprehensive API tests with pytest and TestClient."""

from tests.conftest import authenticated_client as client

# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestHealth:
    def test_root(self):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


# ══════════════════════════════════════════════════════════════════════════════
# STUDENT TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestStudents:
    def _create_student(self, name="João Victor", email="joao@example.com"):
        return client.post("/students", json={"name": name, "email": email})

    def test_create_student(self):
        response = self._create_student()
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "João Victor"
        assert data["email"] == "joao@example.com"
        assert "id" in data
        assert "created_at" in data

    def test_create_student_with_profile(self):
        response = client.post(
            "/students",
            json={
                "name": "Maria",
                "email": "maria@example.com",
                "profile": {"bio": "Developer", "avatar_url": "https://example.com/avatar.png"},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["profile"]["bio"] == "Developer"
        assert data["profile"]["avatar_url"] == "https://example.com/avatar.png"

    def test_create_student_duplicate_email(self):
        self._create_student()
        response = self._create_student()
        assert response.status_code == 400
        assert "Email already registered" in response.json()["detail"]

    def test_create_student_invalid_email(self):
        response = client.post("/students", json={"name": "Test", "email": "not-an-email"})
        assert response.status_code == 422

    def test_create_student_name_too_short(self):
        response = client.post("/students", json={"name": "A", "email": "a@b.com"})
        assert response.status_code == 422

    def test_list_students(self):
        self._create_student("Alice", "alice@example.com")
        self._create_student("Bob", "bob@example.com")
        response = client.get("/students")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_list_students_pagination(self):
        for i in range(5):
            self._create_student(f"Student {i}", f"student{i}@example.com")
        response = client.get("/students?skip=2&limit=2")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_get_student(self):
        create_resp = self._create_student()
        student_id = create_resp.json()["id"]
        response = client.get(f"/students/{student_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "João Victor"

    def test_get_student_not_found(self):
        response = client.get("/students/999")
        assert response.status_code == 404

    def test_update_student(self):
        create_resp = self._create_student()
        student_id = create_resp.json()["id"]
        response = client.patch(f"/students/{student_id}", json={"name": "João Updated"})
        assert response.status_code == 200
        assert response.json()["name"] == "João Updated"

    def test_update_student_not_found(self):
        response = client.patch("/students/999", json={"name": "Ghost"})
        assert response.status_code == 404

    def test_delete_student(self):
        create_resp = self._create_student()
        student_id = create_resp.json()["id"]
        response = client.delete(f"/students/{student_id}")
        assert response.status_code == 204
        assert client.get(f"/students/{student_id}").status_code == 404

    def test_delete_student_not_found(self):
        response = client.delete("/students/999")
        assert response.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# PROFILE TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestProfiles:
    def _create_student(self):
        resp = client.post("/students", json={"name": "Ana", "email": "ana@example.com"})
        return resp.json()["id"]

    def test_create_profile(self):
        student_id = self._create_student()
        response = client.post(
            f"/students/{student_id}/profile",
            json={"bio": "Full-stack dev", "avatar_url": "https://img.com/ana.jpg"},
        )
        assert response.status_code == 201
        assert response.json()["bio"] == "Full-stack dev"

    def test_create_duplicate_profile(self):
        student_id = self._create_student()
        client.post(f"/students/{student_id}/profile", json={"bio": "First"})
        response = client.post(f"/students/{student_id}/profile", json={"bio": "Second"})
        assert response.status_code == 400

    def test_create_profile_student_not_found(self):
        response = client.post("/students/999/profile", json={"bio": "X"})
        assert response.status_code == 400

    def test_update_profile(self):
        student_id = self._create_student()
        client.post(f"/students/{student_id}/profile", json={"bio": "Old bio"})
        response = client.patch(f"/students/{student_id}/profile", json={"bio": "New bio"})
        assert response.status_code == 200
        assert response.json()["bio"] == "New bio"

    def test_update_profile_not_found(self):
        response = client.patch("/students/999/profile", json={"bio": "X"})
        assert response.status_code == 404

    def test_cascade_delete_profile(self):
        """Deleting a student should cascade-delete their profile."""
        student_id = self._create_student()
        client.post(f"/students/{student_id}/profile", json={"bio": "Will be deleted"})
        client.delete(f"/students/{student_id}")
        # Student gone → profile also gone
        assert client.get(f"/students/{student_id}").status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# PROJECT TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestProjects:
    def _create_project(self, name="TaskFlow", description="A project management tool"):
        return client.post("/projects", json={"name": name, "description": description})

    def test_create_project(self):
        response = self._create_project()
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "TaskFlow"
        assert data["tasks"] == []

    def test_list_projects(self):
        self._create_project("Project A")
        self._create_project("Project B")
        response = client.get("/projects")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_get_project(self):
        create_resp = self._create_project()
        project_id = create_resp.json()["id"]
        response = client.get(f"/projects/{project_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "TaskFlow"

    def test_get_project_not_found(self):
        assert client.get("/projects/999").status_code == 404

    def test_update_project(self):
        create_resp = self._create_project()
        project_id = create_resp.json()["id"]
        response = client.patch(f"/projects/{project_id}", json={"name": "TaskFlow v2"})
        assert response.status_code == 200
        assert response.json()["name"] == "TaskFlow v2"

    def test_update_project_not_found(self):
        assert client.patch("/projects/999", json={"name": "X"}).status_code == 404

    def test_delete_project(self):
        create_resp = self._create_project()
        project_id = create_resp.json()["id"]
        assert client.delete(f"/projects/{project_id}").status_code == 204
        assert client.get(f"/projects/{project_id}").status_code == 404

    def test_delete_project_not_found(self):
        assert client.delete("/projects/999").status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# TASK TESTS
# ══════════════════════════════════════════════════════════════════════════════


class TestTasks:
    def _create_project(self):
        resp = client.post("/projects", json={"name": "My Project"})
        return resp.json()["id"]

    def _create_task(self, project_id, title="Fix bug", status="todo"):
        return client.post(
            f"/projects/{project_id}/tasks",
            json={"title": title, "description": "Important task", "status": status},
        )

    def test_create_task(self):
        project_id = self._create_project()
        response = self._create_task(project_id)
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Fix bug"
        assert data["status"] == "todo"
        assert data["project_id"] == project_id

    def test_create_task_in_progress(self):
        project_id = self._create_project()
        response = self._create_task(project_id, "WIP task", "in_progress")
        assert response.status_code == 201
        assert response.json()["status"] == "in_progress"

    def test_create_task_invalid_status(self):
        project_id = self._create_project()
        response = client.post(
            f"/projects/{project_id}/tasks",
            json={"title": "Bad", "status": "invalid_status"},
        )
        assert response.status_code == 422

    def test_create_task_project_not_found(self):
        response = client.post("/projects/999/tasks", json={"title": "Orphan task"})
        assert response.status_code == 404

    def test_list_tasks(self):
        project_id = self._create_project()
        self._create_task(project_id, "Task 1")
        self._create_task(project_id, "Task 2")
        response = client.get(f"/projects/{project_id}/tasks")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_get_task(self):
        project_id = self._create_project()
        task_resp = self._create_task(project_id)
        task_id = task_resp.json()["id"]
        response = client.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["title"] == "Fix bug"

    def test_get_task_not_found(self):
        assert client.get("/tasks/999").status_code == 404

    def test_update_task_status(self):
        project_id = self._create_project()
        task_resp = self._create_task(project_id)
        task_id = task_resp.json()["id"]
        response = client.patch(f"/tasks/{task_id}", json={"status": "done"})
        assert response.status_code == 200
        assert response.json()["status"] == "done"

    def test_update_task_not_found(self):
        assert client.patch("/tasks/999", json={"title": "X"}).status_code == 404

    def test_delete_task(self):
        project_id = self._create_project()
        task_resp = self._create_task(project_id)
        task_id = task_resp.json()["id"]
        assert client.delete(f"/tasks/{task_id}").status_code == 204
        assert client.get(f"/tasks/{task_id}").status_code == 404

    def test_delete_task_not_found(self):
        assert client.delete("/tasks/999").status_code == 404

    def test_cascade_delete_tasks_with_project(self):
        """Deleting a project should cascade-delete all its tasks."""
        project_id = self._create_project()
        task_resp = self._create_task(project_id)
        task_id = task_resp.json()["id"]
        client.delete(f"/projects/{project_id}")
        assert client.get(f"/tasks/{task_id}").status_code == 404

    def test_project_response_includes_tasks(self):
        """GET /projects/{id} should include nested tasks."""
        project_id = self._create_project()
        self._create_task(project_id, "Nested task")
        response = client.get(f"/projects/{project_id}")
        data = response.json()
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["title"] == "Nested task"
